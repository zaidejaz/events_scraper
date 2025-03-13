import os
from flask import Blueprint, jsonify, render_template, request, current_app
from datetime import datetime, timedelta

from flask_login import login_required
from src.scraper.scheduler import scheduler, ScraperScheduler
from src.ticketmaster.api import TicketmasterAPI
from ..todaytix.api import TodayTixAPI
from ..scraper.scraper import EventScraper
from ..models.database import Event, ScraperJob, db
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import send_file
from ..services import UploadService  

bp = Blueprint('scraper', __name__)

@bp.route('/scrape')
@login_required
def scrape_page():
    cleanup_old_files()
    current_job = ScraperJob.query.order_by(ScraperJob.id.desc()).first()
    return render_template('scrape.html', current_job=current_job)

@bp.route('/api/scrape/start', methods=['POST'])
@login_required
def start_scrape():
    try:
        data = request.json
        interval_minutes = data.get('interval_minutes', 20)
        concurrent_requests = data.get('concurrent_requests', 5)
        auto_upload = data.get('auto_upload', False)
        
        events = Event.query.all()
        if not events:
            return jsonify({
                "status": "error",
                "message": "No events found in database"
            }), 400

        os.makedirs(current_app.config['OUTPUT_FILE_DIR'], exist_ok=True)

        # Stop any existing running jobs first
        stop_all_running_jobs()

        job = ScraperJob.query.order_by(ScraperJob.id.desc()).first()
        if not job:
            job = ScraperJob(
                status='running',
                interval_minutes=interval_minutes,
                concurrent_requests=concurrent_requests,
                auto_upload=auto_upload,
                events_processed=0,
                total_tickets_found=0,
                last_run=None,
                next_run=datetime.now()
            )
            db.session.add(job)
        else:
            job.status = 'running'
            job.interval_minutes = interval_minutes
            job.concurrent_requests = concurrent_requests
            job.auto_upload = auto_upload
            job.events_processed = 0
            job.total_tickets_found = 0
            job.next_run = datetime.now()
        
        db.session.commit()

        job_id = job.id
        app = current_app._get_current_object() 
        output_dir = current_app.config['OUTPUT_FILE_DIR']

        def run_scraper(app, job_id, output_dir, interval_minutes):
            with app.app_context():
                try:
                    job = ScraperJob.query.get(job_id)
                    if not job or job.status != 'running':
                        return

                    app.logger.info(f"Job {job_id} settings - auto_upload: {job.auto_upload}, concurrent_requests: {job.concurrent_requests}")

                    todaytix_api = TodayTixAPI()
                    ticketmaster_api = TicketmasterAPI()
                    scraper = EventScraper(
                        todaytix_api=todaytix_api, 
                        ticketmaster_api=ticketmaster_api,
                        output_dir=output_dir,
                        concurrent_requests=job.concurrent_requests,
                        auto_upload=job.auto_upload  
                    )

                    app.logger.info(f"Scraper settings - auto_upload: {scraper.auto_upload}, max_concurrent: {scraper.max_concurrent}")

                    success, output_file = scraper.run(job)

                    app.logger.info(f"Scraper run completed - success: {success}, output_file: {output_file}, auto_upload setting: {scraper.auto_upload}")

                    job = ScraperJob.query.get(job_id)
                    if not job or job.status == 'stopped':
                        return

                    if success and output_file:
                        app.logger.info(f"Checking auto_upload setting for job {job_id}: {job.auto_upload}")

                        if job.auto_upload:
                            app.logger.info(f"Starting file upload for job {job_id}")
                            try:
                                upload_service = UploadService(
                                    api_base_url=app.config['STORE_API_BASE_URL'],
                                    api_key=app.config['STORE_API_KEY'],
                                    company_id=app.config['COMPANY_ID']
                                )
                                upload_success, message = upload_service.upload_csv(output_file)

                                if upload_success:
                                    app.logger.info(f"Scheduled job {job_id}: File uploaded successfully")
                                else:
                                    app.logger.error(f"Scheduled job {job_id}: File upload failed - {message}")
                            except Exception as e:
                                app.logger.error(f"Scheduled job {job_id}: Upload error - {str(e)}")
                        else:
                            app.logger.info(f"Auto upload disabled for job {job_id}, skipping upload")

                        job.status = 'completed'
                        job.last_run = datetime.now()
                        job.next_run = job.last_run + timedelta(minutes=interval_minutes)

                        if job.status != 'stopped':
                            scheduler.add_job(
                                func=ScraperScheduler.start_scraper,
                                trigger='date',
                                run_date=job.next_run,
                                args=[job_id, app],
                                id=f'scraper_{job_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                            )

                            cleanup_job_id = f'cleanup_{job_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                            scheduler.add_job(
                                func=cleanup_old_files,
                                trigger='date',
                                run_date=datetime.now() + timedelta(hours=24),
                                id=cleanup_job_id
                            )
                    else:
                        job.status = 'error'
                        job.next_run = None

                    db.session.commit()
                except Exception as e:
                    app.logger.error(f"Error in scraper thread: {str(e)}")
                    job = ScraperJob.query.get(job_id)
                    if job:
                        job.status = 'error'
                        job.next_run = None
                        db.session.commit()

        import threading
        thread = threading.Thread(
            target=run_scraper,
            args=(app, job_id, output_dir, interval_minutes)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            "status": "success",
            "message": "Scraper started successfully"
        })

    except Exception as e:
        if 'job' in locals():
            job.status = 'error'
            job.next_run = None
            db.session.commit()
            
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

def stop_all_running_jobs():
    """Helper function to stop all running jobs and clean up"""
    # Stop all running scraper jobs
    running_jobs = ScraperJob.query.filter(ScraperJob.status.in_(['running', 'completed'])).all()
    for job in running_jobs:
        job.status = 'stopped'
        job.next_run = None
        
        # Remove all scheduled jobs for this job_id
        jobs = scheduler.get_jobs()
        for scheduled_job in jobs:
            if scheduled_job.id.startswith(f'scraper_{job.id}_'):
                scheduler.remove_job(scheduled_job.id)
            elif scheduled_job.id.startswith(f'cleanup_{job.id}_'):
                scheduler.remove_job(scheduled_job.id)
    
    db.session.commit()

@bp.route('/api/scrape/stop', methods=['POST'])
@login_required
def stop_scrape():
    try:
        stop_all_running_jobs()
        return jsonify({
            "status": "success",
            "message": "Scraper stopped and all scheduled jobs removed"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bp.route('/api/scrape/status')
@login_required
def get_status():
    try:
        # Get the most recent job
        job = ScraperJob.query.order_by(ScraperJob.id.desc()).first()
        
        if job:
            return jsonify({
                "status": job.status,
                "last_run": job.last_run.isoformat() if job.last_run else None,
                "next_run": job.next_run.isoformat() if job.next_run else None,
                "events_processed": job.events_processed,
                "total_tickets_found": job.total_tickets_found,
                "interval_minutes": job.interval_minutes,
                "concurrent_requests": job.concurrent_requests,
                "auto_upload": job.auto_upload
            })
        else:
            return jsonify({
                "status": "stopped",
                "last_run": None,
                "next_run": None,
                "events_processed": 0,
                "total_tickets_found": 0,
                "concurrent_requests": 5,
                "auto_upload": False
            })
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
    
def get_file_info(file_path):
    """Get file information including creation time and age"""
    stat = os.stat(file_path)
    created_time = datetime.fromtimestamp(stat.st_ctime)
    age_hours = (datetime.now() - created_time).total_seconds() / 3600
    return {
        'name': os.path.basename(file_path),
        'created_at': created_time.isoformat(),
        'size': stat.st_size,
        'age_hours': age_hours
    }

def get_output_dir():
    """Get absolute path to output directory"""
    base_dir = current_app.config.get('BASE_DIR', Path(__file__).resolve().parent.parent.parent)
    output_dir = current_app.config['OUTPUT_FILE_DIR']
    
    # If output_dir is relative, make it absolute relative to base_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(base_dir, output_dir)
        current_app.logger.debug(f"Output directory: {output_dir}")
    # Ensure directory exists
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

@bp.route('/api/files', methods=['GET'])
@login_required
def list_files():
    try:
        output_dir = Path(get_output_dir())
        files = []
        
        current_app.logger.info(f"Scanning directory: {output_dir}")
        
        if not output_dir.exists():
            current_app.logger.error(f"Output directory does not exist: {output_dir}")
            return jsonify({
                "status": "error",
                "message": "Output directory not found"
            }), 500
            
        # Only look for .xlsx files
        for file_path in output_dir.glob('*.csv'):
            try:
                file_info = get_file_info(str(file_path))
                files.append(file_info)
            except Exception as e:
                current_app.logger.error(f"Error processing file {file_path}: {str(e)}")
                continue
        
        # Sort files by creation time, newest first
        files.sort(key=lambda x: x['created_at'], reverse=True)
        
        return jsonify({
            "status": "success",
            "files": files
        })
    except Exception as e:
        current_app.logger.error(f"Error listing files: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@bp.route('/api/files/<filename>', methods=['GET'])
@login_required
def download_file(filename):
    try:
        # Verify file extension
        if not filename.lower().endswith('.csv'):
            return jsonify({
                "status": "error",
                "message": "Only Excel (.xlsx) files can be downloaded"
            }), 400
            
        output_dir = get_output_dir()
        safe_filename = secure_filename(filename)
        file_path = os.path.join(output_dir, safe_filename)
        
        current_app.logger.info(f"Attempting to download file: {file_path}")
        
        if not os.path.exists(file_path):
            current_app.logger.error(f"File not found: {file_path}")
            return jsonify({
                "status": "error",
                "message": "File not found"
            }), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=safe_filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading file: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

def cleanup_old_files():
    """Delete files older than 24 hours"""
    output_dir = Path(get_output_dir())
    current_app.logger.info(f"Running cleanup in: {output_dir}")
    
    for file_path in output_dir.glob('*'):
        if file_path.is_file():
            try:
                age_hours = (datetime.now() - datetime.fromtimestamp(file_path.stat().st_ctime)).total_seconds() / 3600
                if age_hours >= 24:
                    current_app.logger.info(f"Deleting old file: {file_path}")
                    file_path.unlink()
            except Exception as e:
                current_app.logger.error(f"Error deleting file {file_path}: {str(e)}")