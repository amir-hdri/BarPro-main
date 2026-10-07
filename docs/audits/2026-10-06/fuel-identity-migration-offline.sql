BEGIN;

-- Running upgrade 041_driver_plate_tracking_fields -> 042_fuel_request_identity

ALTER TABLE fuel_inquiries ADD COLUMN plate_number_snapshot VARCHAR(50);

ALTER TABLE fuel_inquiries ADD COLUMN driver_name_snapshot VARCHAR(255);

ALTER TABLE fuel_inquiries ADD COLUMN started_at TIMESTAMP WITHOUT TIME ZONE;

ALTER TABLE fuel_inquiries ADD COLUMN finished_at TIMESTAMP WITHOUT TIME ZONE;

UPDATE alembic_version SET version_num='042_fuel_request_identity' WHERE alembic_version.version_num = '041_driver_plate_tracking_fields';

COMMIT;

