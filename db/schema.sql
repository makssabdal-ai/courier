-- Courier Delivery Management System
-- Database Schema

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role        VARCHAR(20)  NOT NULL CHECK (role IN ('driver', 'manager', 'courier')),
    full_name   VARCHAR(100) NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Batch input sessions created by driver
CREATE TABLE IF NOT EXISTS delivery_sessions (
    id          SERIAL PRIMARY KEY,
    driver_id   INTEGER REFERENCES users(id),
    status      VARCHAR(20)  DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed')),
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS packages (
    id                      SERIAL PRIMARY KEY,
    track_number            VARCHAR(20)  UNIQUE NOT NULL,
    internal_number         VARCHAR(15),
    sender_name             VARCHAR(100) NOT NULL,
    sender_address          VARCHAR(255) NOT NULL,
    recipient_name          VARCHAR(100) NOT NULL,
    recipient_address       VARCHAR(255) NOT NULL,
    recipient_phone         VARCHAR(20),
    status                  VARCHAR(50)  NOT NULL DEFAULT 'pending',
    -- pending | delivered_to_office | ready_for_delivery | delivered
    -- delivery_failed | error_missing | returned_to_sender
    delivery_fail_count     INTEGER      DEFAULT 0,
    expeditor_delivery_date TIMESTAMP,   -- when driver brought to local office
    ready_date              TIMESTAMP,   -- when status changed to ready_for_delivery
    planned_delivery_date   DATE,        -- for courier's date-based view
    session_id              INTEGER REFERENCES delivery_sessions(id),
    created_by              INTEGER REFERENCES users(id),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Monthly counter for internal numbers (resets each month)
CREATE TABLE IF NOT EXISTS monthly_counter (
    year    INTEGER NOT NULL,
    month   INTEGER NOT NULL,
    counter INTEGER DEFAULT 0,
    PRIMARY KEY (year, month)
);

-- Waybills (накладные)
CREATE TABLE IF NOT EXISTS waybills (
    id            SERIAL PRIMARY KEY,
    waybill_type  VARCHAR(20) NOT NULL CHECK (waybill_type IN ('delivery', 'return', 'missing')),
    delivery_date DATE,
    created_by    INTEGER REFERENCES users(id),
    status        VARCHAR(20) DEFAULT 'active',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS waybill_items (
    id          SERIAL PRIMARY KEY,
    waybill_id  INTEGER REFERENCES waybills(id) ON DELETE CASCADE,
    package_id  INTEGER REFERENCES packages(id),
    sort_order  INTEGER DEFAULT 0,
    note        TEXT
);

-- Audit log for package status changes
CREATE TABLE IF NOT EXISTS package_history (
    id          SERIAL PRIMARY KEY,
    package_id  INTEGER REFERENCES packages(id),
    old_status  VARCHAR(50),
    new_status  VARCHAR(50),
    changed_by  INTEGER REFERENCES users(id),
    notes       TEXT,
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION log_package_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO package_history (package_id, old_status, new_status, changed_at)
        VALUES (NEW.id, OLD.status, NEW.status, NOW());
    END IF;
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_package_status ON packages;
CREATE TRIGGER trg_package_status
BEFORE UPDATE ON packages
FOR EACH ROW EXECUTE FUNCTION log_package_status_change();


CREATE OR REPLACE FUNCTION next_internal_number() RETURNS VARCHAR AS $$
DECLARE
    v_year    INTEGER := EXTRACT(YEAR FROM NOW())::INTEGER;
    v_month   INTEGER := EXTRACT(MONTH FROM NOW())::INTEGER;
    v_day     INTEGER := EXTRACT(DAY FROM NOW())::INTEGER;
    v_counter INTEGER;
BEGIN
    INSERT INTO monthly_counter (year, month, counter)
    VALUES (v_year, v_month, 1)
    ON CONFLICT (year, month) DO UPDATE
        SET counter = monthly_counter.counter + 1
    RETURNING counter INTO v_counter;

    RETURN LPAD(v_day::TEXT, 2, '0') || LPAD(v_month::TEXT, 2, '0') || '-' || LPAD(v_counter::TEXT, 6, '0');
END;
$$ LANGUAGE plpgsql;
