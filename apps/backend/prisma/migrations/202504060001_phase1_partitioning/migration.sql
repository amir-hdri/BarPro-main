-- Prisma creates the base tables, but PostgreSQL partitioning for the Job table
-- is maintained as raw SQL because Prisma does not model declarative partitions.

CREATE TABLE IF NOT EXISTS "JobPartitioned" (
  LIKE "Job" INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES
) PARTITION BY RANGE ("createdAt");

INSERT INTO "JobPartitioned"
SELECT * FROM "Job"
ON CONFLICT DO NOTHING;

ALTER TABLE "Job" RENAME TO "Job_unpartitioned";
ALTER TABLE "JobPartitioned" RENAME TO "Job";

ALTER INDEX IF EXISTS "Job_pkey" RENAME TO "Job_unpartitioned_pkey";
ALTER INDEX IF EXISTS "JobPartitioned_pkey" RENAME TO "Job_pkey";

CREATE OR REPLACE FUNCTION create_job_daily_partition(target_date date)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  partition_name text := format('Job_%s', to_char(target_date, 'YYYYMMDD'));
  next_date date := target_date + interval '1 day';
BEGIN
  EXECUTE format(
    'CREATE TABLE IF NOT EXISTS %I PARTITION OF "Job" FOR VALUES FROM (%L) TO (%L);',
    partition_name,
    target_date,
    next_date
  );
END;
$$;

SELECT create_job_daily_partition(CURRENT_DATE);
SELECT create_job_daily_partition(CURRENT_DATE + interval '1 day');

CREATE OR REPLACE FUNCTION drop_old_job_partitions(retention_days integer)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
  partition_record record;
  cutoff_date date := CURRENT_DATE - retention_days;
BEGIN
  FOR partition_record IN
    SELECT inhrelid::regclass::text AS partition_name
    FROM pg_inherits
    WHERE inhparent = '"Job"'::regclass
  LOOP
    IF substring(partition_record.partition_name from 'Job_(\d{8})') IS NOT NULL THEN
      IF to_date(substring(partition_record.partition_name from 'Job_(\d{8})'), 'YYYYMMDD') < cutoff_date THEN
        EXECUTE format('DROP TABLE IF EXISTS %I;', partition_record.partition_name);
      END IF;
    END IF;
  END LOOP;
END;
$$;
