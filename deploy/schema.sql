-- VPN SaaS reference schema (SQLite-oriented). Order respects FKs.

CREATE TABLE IF NOT EXISTS nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(64) NOT NULL UNIQUE,
  region VARCHAR(16) NOT NULL,
  base_url VARCHAR(255) NOT NULL,
  username VARCHAR(64) NOT NULL,
  password VARCHAR(128) NOT NULL,
  inbound_id INTEGER NOT NULL,
  verify_ssl BOOLEAN NOT NULL DEFAULT 1,
  public_host VARCHAR(255),
  is_enabled BOOLEAN NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username VARCHAR(64) NOT NULL UNIQUE,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  uuid VARCHAR(64) NOT NULL UNIQUE,
  vless_link TEXT NOT NULL,
  current_node_id INTEGER REFERENCES nodes(id),
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS user_node_accesses (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  node_id INTEGER NOT NULL REFERENCES nodes(id),
  uuid VARCHAR(64) NOT NULL,
  vless_link TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  UNIQUE (user_id, node_id)
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(64) NOT NULL UNIQUE,
  price NUMERIC(12, 2) NOT NULL,
  traffic_limit_gb REAL NOT NULL,
  duration_days INTEGER NOT NULL,
  is_enabled BOOLEAN NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  started_at DATETIME NOT NULL,
  expires_at DATETIME NOT NULL,
  traffic_limit_gb REAL NOT NULL,
  traffic_remaining_gb REAL NOT NULL,
  created_at DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_expires_at ON subscriptions (expires_at);
CREATE INDEX IF NOT EXISTS ix_plans_is_enabled ON plans (is_enabled);

CREATE TABLE IF NOT EXISTS payment_orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_order_id VARCHAR(64) NOT NULL UNIQUE,
  user_id INTEGER NOT NULL REFERENCES users(id),
  user_email VARCHAR(120) NOT NULL,
  plan_slug VARCHAR(32) NOT NULL,
  period_key VARCHAR(32) NOT NULL,
  plan_label VARCHAR(64) NOT NULL,
  period_label VARCHAR(64) NOT NULL,
  amount NUMERIC(12, 2) NOT NULL,
  alipay_trade_no VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'waiting',
  traffic_gb REAL NOT NULL,
  duration_days INTEGER NOT NULL,
  plan_id INTEGER NOT NULL REFERENCES plans(id),
  client_uuid VARCHAR(64),
  subscription_url TEXT,
  created_at DATETIME NOT NULL,
  completed_at DATETIME
);

CREATE INDEX IF NOT EXISTS ix_payment_orders_user_id ON payment_orders (user_id);
CREATE INDEX IF NOT EXISTS ix_payment_orders_status ON payment_orders (status);
CREATE INDEX IF NOT EXISTS ix_payment_orders_public_order_id ON payment_orders (public_order_id);
CREATE INDEX IF NOT EXISTS ix_payment_orders_alipay ON payment_orders (alipay_trade_no);
