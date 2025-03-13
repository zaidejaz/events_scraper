def generate_inventory_id(event_name: str, date: str, row: str) -> str:
    """Generate a unique inventory ID."""
    event_code = ''.join([c.upper() for c in event_name if c.isalpha()][:5])
    event_numeric = ''.join(str(ord(c) - 64) for c in event_code)
    date_numeric = date.replace("/", "")
    if row.isdigit():
        row_numeric = row
    else:
        row_numeric = ''.join(str(ord(c.upper()) - 64) for c in row)
    return f"{date_numeric}{event_numeric}{row_numeric}"
