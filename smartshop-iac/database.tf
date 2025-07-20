variable "db_name" {
  description = "The name of the PostgreSQL database"
  type        = string
  default     = "smartshop"
}

variable "db_user" {
  description = "The username for the PostgreSQL database. Must be 1 to 63 letters, numbers, or underscores. The first character must be a letter."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9_]{0,62}$", var.db_user))
    error_message = "The master username must be 1 to 63 characters long, start with a letter, and contain only letters, numbers, or underscores."
  }
  validation {
    condition     = lower(var.db_user) != "postgres"
    error_message = "The master username cannot be 'postgres' or other reserved keywords."
  }
}

variable "db_password" {
  description = "The password for the PostgreSQL database"
  type        = string
  sensitive   = true
}

# Create a DB Subnet Group to place the RDS instance in private subnets
resource "aws_db_subnet_group" "main" {
  name       = "smartshop-db-subnet-group"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "SmartShop DB Subnet Group"
  }
}

# Create a dedicated Security Group for the RDS instance
resource "aws_security_group" "rds_sg" {
  name        = "smartshop-rds-sg"
  description = "Allow traffic to RDS from the applications private security group"
  vpc_id      = aws_vpc.main.id

  # Allow PostgreSQL traffic from the private app security group
  ingress {
    description     = "PostgreSQL from private app instances"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.private_sg.id]
  }

  tags = {
    Name = "smartshop-rds-sg"
  }
}

# Create the RDS PostgreSQL instance
resource "aws_db_instance" "main" {
  allocated_storage      = 20
  engine                 = "postgres"
  engine_version         = "14" # Matches your docker-compose image
  instance_class         = "db.t3.micro"
  db_name                = var.db_name
  username               = var.db_user
  password               = var.db_password
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  skip_final_snapshot    = true
  publicly_accessible    = false # Keep the database private
}