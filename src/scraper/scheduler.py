from flask_apscheduler import APScheduler
from datetime import datetime, timedelta

from src.ticketmaster.api import TicketmasterAPI
from ..models.database import db, ScraperJob
from ..todaytix.api import TodayTixAPI
from .scraper import EventScraper
import logging

logger = logging.getLogger(__name__)
scheduler = APScheduler()

class ScraperScheduler:
    @staticmethod
    def start_scraper(job_id: int, app):
        with app.app_context():
            job = ScraperJob.query.get(job_id)
            if not job:
                logger.error(f"Job {job_id} not found")
                return
            
            try:
                if job.status == 'stopped':
                    logger.info(f"Job {job_id} is stopped, not running")
                    return

                logger.info(f"Starting scheduled job {job_id} with settings from DB:")
                logger.info(f"- Auto Upload: {job.auto_upload}")
                logger.info(f"- Concurrent Requests: {job.concurrent_requests}")
                logger.info(f"- Interval Minutes: {job.interval_minutes}")
                
                job.status = 'running'
                job.events_processed = 0
                job.total_tickets_found = 0
                job.last_run = datetime.now()
                job.next_run = job.last_run + timedelta(minutes=job.interval_minutes)
                db.session.commit()
                
                logger.info(f"Job {job_id} started. Next run scheduled at {job.next_run}")
                
                todaytix_api = TodayTixAPI()
                ticketmaster_api = TicketmasterAPI()
                scraper = EventScraper(
                    todaytix_api=todaytix_api, 
                    ticketmaster_api=ticketmaster_api,
                    output_dir=app.config['OUTPUT_FILE_DIR'],
                    concurrent_requests=job.concurrent_requests,  
                    auto_upload=job.auto_upload 
                )

                logger.info(f"Initialized scraper with settings - auto_upload: {scraper.auto_upload}, concurrent_requests: {scraper.max_concurrent}")
                
                success, output_file = scraper.run(job)
                
                logger.info(f"Scraper run completed - success: {success}, output_file: {output_file}")

                if success and output_file:
                    if job.status != 'stopped':
                        next_run = datetime.now() + timedelta(minutes=job.interval_minutes)
                        scheduler.add_job(
                            func=ScraperScheduler.start_scraper,
                            trigger='date',
                            run_date=next_run,
                            args=[job_id, app],
                            id=f'scraper_{job_id}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
                        )
                        logger.info(f"Next run scheduled for job {job_id} at {next_run}")
                    
                    job.status = 'completed'
                else:
                    job.status = 'error'
                    job.next_run = None
                    logger.error(f"Scraper run failed for job {job_id}")
                
                db.session.commit()
                
            except Exception as e:
                logger.error(f"Error in scheduled job {job_id}: {str(e)}")
                try:
                    job = ScraperJob.query.get(job_id)
                    if job:
                        job.status = 'error'
                        job.next_run = None
                        db.session.commit()
                except Exception as inner_e:
                    logger.error(f"Error updating job status: {str(inner_e)}")
                raise e