"""Small in-place schema upgrades. `create_all` adds new tables but not new columns of existing ones."""
from sqlalchemy import text
from sqlalchemy.engine import Engine

STEPS = [
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS color VARCHAR(9)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS color VARCHAR(9)",
    "ALTER TABLE clients ADD COLUMN IF NOT EXISTS job_code VARCHAR(4)",
    "ALTER TABLE requests ADD COLUMN IF NOT EXISTS inspector_ids JSON",
    "ALTER TABLE job_lines ADD COLUMN IF NOT EXISTS grp INTEGER",
    "ALTER TABLE job_lines ADD COLUMN IF NOT EXISTS inspector_currency VARCHAR(3)",
    "ALTER TABLE job_lines ADD COLUMN IF NOT EXISTS snap_fx_insp NUMERIC(12, 4)",
    # one group per inspector on a job (older data had one line per inspector and month)
    """UPDATE job_lines jl SET grp = s.rn FROM (
         SELECT id, dense_rank() OVER (PARTITION BY job_id ORDER BY coalesce(inspector_id, 0)) AS rn FROM job_lines
       ) s WHERE jl.id = s.id AND jl.grp IS NULL""",
    "ALTER TABLE job_lines ALTER COLUMN grp SET DEFAULT 1",
    # the request inspector becomes the first of the CV list
    """UPDATE requests SET inspector_ids = json_build_array(inspector_id)
       WHERE inspector_id IS NOT NULL AND inspector_ids IS NULL""",
    # «CV отправлены» is no longer a separate status
    "UPDATE requests SET status = 'В процессе' WHERE status = 'CV отправлены'",
]


def upgrade(engine: Engine):
    with engine.begin() as c:
        for s in STEPS:
            c.execute(text(s))
