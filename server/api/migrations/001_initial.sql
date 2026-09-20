BEGIN IMMEDIATE;
CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, appliedAt TEXT NOT NULL);
CREATE TABLE service_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1), version INTEGER NOT NULL DEFAULT 1,
    acceptingBookings INTEGER NOT NULL DEFAULT 0 CHECK (acceptingBookings IN (0,1)),
    acceptingFeedback INTEGER NOT NULL DEFAULT 0 CHECK (acceptingFeedback IN (0,1)),
    closedMessage TEXT NOT NULL DEFAULT '暂未开放提交，可以先通过 QQ 联系我们。'
);
INSERT INTO service_settings (id) VALUES (1);
CREATE TABLE bookings (
    id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
    idempotencyKey TEXT NOT NULL UNIQUE, payloadHash TEXT,
    name TEXT NOT NULL, gradeMajor TEXT NOT NULL, phone TEXT NOT NULL, qq TEXT NOT NULL,
    email TEXT NOT NULL, device TEXT NOT NULL, os TEXT NOT NULL, issue TEXT NOT NULL,
    preferredContactTime TEXT NOT NULL,
    consent INTEGER NOT NULL CHECK (consent = 1), consentVersion TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','scheduled','in_progress','completed','cancelled')),
    notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, closedAt TEXT, purgedAt TEXT
);
CREATE TABLE feedback (
    id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE,
    idempotencyKey TEXT NOT NULL UNIQUE, payloadHash TEXT,
    nameMajor TEXT NOT NULL, contactType TEXT NOT NULL CHECK (contactType IN ('qq','phone')),
    contact TEXT NOT NULL, bookingReference TEXT NOT NULL, bookingId TEXT REFERENCES bookings(id),
    serviceTypes TEXT NOT NULL, summary TEXT NOT NULL, volunteerNames TEXT NOT NULL,
    reportedHoursX100 INTEGER NOT NULL CHECK (reportedHoursX100 BETWEEN 1 AND 500),
    confirmedHoursX100 INTEGER CHECK (confirmedHoursX100 BETWEEN 0 AND 500),
    requestedOn TEXT NOT NULL,
    attitudeRating INTEGER NOT NULL CHECK (attitudeRating BETWEEN 1 AND 5),
    skillRating INTEGER NOT NULL CHECK (skillRating BETWEEN 1 AND 5),
    overallRating INTEGER NOT NULL CHECK (overallRating BETWEEN 1 AND 5), comment TEXT NOT NULL,
    consent INTEGER NOT NULL CHECK (consent = 1), consentVersion TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','reviewed','invalid')),
    notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
    createdAt TEXT NOT NULL, updatedAt TEXT NOT NULL, closedAt TEXT, purgedAt TEXT
);
CREATE INDEX bookings_status_created ON bookings(status, createdAt);
CREATE INDEX bookings_created ON bookings(createdAt);
CREATE INDEX feedback_status_created ON feedback(status, createdAt);
CREATE INDEX feedback_created ON feedback(createdAt);
CREATE INDEX feedback_booking ON feedback(bookingId);
CREATE TABLE record_events (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, recordId TEXT NOT NULL,
    actor TEXT NOT NULL, action TEXT NOT NULL, changes TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '', createdAt TEXT NOT NULL
);
CREATE INDEX events_record ON record_events(kind, recordId, id);
INSERT INTO schema_migrations VALUES (1, strftime('%Y-%m-%dT%H:%M:%SZ','now'));
COMMIT;
