CREATE TABLE products (
    product_id VARCHAR(20) PRIMARY KEY, -- Changed from SERIAL to VARCHAR to match products.csv 'id'
    name VARCHAR(255) NOT NULL,
    brand VARCHAR(255),
    category VARCHAR(255),
    price DECIMAL NOT NULL,
    description TEXT,
    stock INTEGER,
    rating DECIMAL(2,1), -- Adjusted to match products.csv 'rating' precision if needed, or keep as DECIMAL
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE reviews (
    review_id SERIAL PRIMARY KEY,
    product_id VARCHAR(20) REFERENCES products(product_id) ON DELETE CASCADE, -- Changed to VARCHAR to match products.product_id
    rating DECIMAL(2,1) NOT NULL, -- Changed from INTEGER to DECIMAL to match reviews.csv 'rating'
    text TEXT,
    review_date DATE, -- Changed to DATE to match reviews.csv 'date' column and store the actual review date
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE TABLE store_policies (
    policy_id SERIAL PRIMARY KEY,
    policy_type VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    conditions TEXT,
    timeframe INTEGER, -- Changed to INTEGER, assuming timeframe in store_policies.csv represents days
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE
);
