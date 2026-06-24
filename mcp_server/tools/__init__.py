# get the absolute directory of the project
from pathlib import Path
basic_dir = Path(__file__).resolve().parent.parent

db = f"{basic_dir}/travel_new.sqlite"  #database file

# The actual database file used in the project
local_file = f"{basic_dir}/travel_new.sqlite"

# backup database which allows us to restart during testing
backup_file = f"{basic_dir}/travel2.sqlite"