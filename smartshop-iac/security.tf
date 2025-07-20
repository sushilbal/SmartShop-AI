# Security Group for public-facing resources (e.g., Load Balancer, Web Server)
resource "aws_security_group" "public_sg" {
  name        = "smartshop-public-sg"
  description = "Allow HTTP and HTTPS inbound traffic"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "smartshop-public-sg"
  }
}

# Security Group for private resources (e.g., App Server, Database)
resource "aws_security_group" "private_sg" {
  name        = "smartshop-private-sg"
  description = "Allow traffic from public security group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Allow all traffic from the public security group"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.public_sg.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "smartshop-private-sg"
  }
}