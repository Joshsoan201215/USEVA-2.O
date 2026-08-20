CREATE TABLE branch (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  name VARCHAR(100) NOT NULL,
  created_at DATETIME
);

CREATE TABLE category (
  id INTEGER PRIMARY KEY,
  name VARCHAR(80) NOT NULL UNIQUE,
  icon VARCHAR(20),
  color VARCHAR(20)
);

CREATE TABLE pantry_item (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  name VARCHAR(160) NOT NULL,
  quantity FLOAT DEFAULT 1,
  unit VARCHAR(30),
  price FLOAT DEFAULT 0,
  purchase_date DATE,
  expiry_date DATE,
  location VARCHAR(80),
  status VARCHAR(30),
  notes TEXT,
  image VARCHAR(255),
  category_id INTEGER REFERENCES category(id),
  created_at DATETIME,
  branch_id INTEGER REFERENCES branch(id)
);

CREATE TABLE receipt (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  store_name VARCHAR(160),
  receipt_date DATE,
  total FLOAT DEFAULT 0,
  image VARCHAR(255),
  image_hash VARCHAR(64),
  receipt_signature VARCHAR(64),
  source VARCHAR(30),
  created_at DATETIME,
  branch_id INTEGER REFERENCES branch(id)
);

CREATE TABLE receipt_item (
  id INTEGER PRIMARY KEY,
  receipt_id INTEGER NOT NULL REFERENCES receipt(id),
  name VARCHAR(160) NOT NULL,
  quantity FLOAT DEFAULT 1,
  unit VARCHAR(30),
  unit_price FLOAT DEFAULT 0,
  category VARCHAR(80),
  purchase_date DATE,
  expiry_date DATE,
  location VARCHAR(80),
  notes TEXT
);

CREATE TABLE shopping_item (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  name VARCHAR(160) NOT NULL,
  quantity FLOAT DEFAULT 1,
  unit VARCHAR(30),
  checked BOOLEAN DEFAULT 0,
  priority VARCHAR(20),
  created_at DATETIME,
  branch_id INTEGER REFERENCES branch(id)
);

CREATE TABLE waste_log (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  item_name VARCHAR(160) NOT NULL,
  quantity FLOAT DEFAULT 1,
  reason VARCHAR(120),
  estimated_value FLOAT DEFAULT 0,
  logged_at DATETIME,
  branch_id INTEGER REFERENCES branch(id)
);
