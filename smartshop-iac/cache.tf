# Security Group for ElastiCache Redis
resource "aws_security_group" "redis_sg" {
  name        = "smartshop-redis-sg"
  description = "Allow Redis traffic from the applications private security group"
  vpc_id      = aws_vpc.main.id

  # Allow Redis traffic (port 6379) from the private app security group
  ingress {
    description     = "Redis from private app instances"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.private_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "smartshop-redis-sg"
  }
}

# Create an ElastiCache Subnet Group
resource "aws_elasticache_subnet_group" "main" {
  name       = "smartshop-cache-subnet-group"
  subnet_ids = aws_subnet.private[*].id
}

# Create the ElastiCache Redis cluster
resource "aws_elasticache_cluster" "main" {
  cluster_id           = "smartshop-redis-cluster"
  engine               = "redis"
  engine_version       = "7.0" # Corresponds to redis:7-alpine in docker-compose
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis_sg.id]
}