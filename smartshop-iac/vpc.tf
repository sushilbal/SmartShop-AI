# Create the Virtual Private Cloud (VPC)
resource "aws_vpc" "main" {
  cidr_block = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "smartshop-vpc"
  }
}

# Create Public Subnets
resource "aws_subnet" "public" {
  count = length(var.public_subnet_cidrs)
  vpc_id     = aws_vpc.main.id
  cidr_block = var.public_subnet_cidrs[count.index]
  availability_zone = tolist(data.aws_availability_zones.available.names)[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "smartshop-public-subnet-${count.index + 1}"
  }
}

# Create Private Subnets
resource "aws_subnet" "private" {
  count = length(var.private_subnet_cidrs)
  vpc_id     = aws_vpc.main.id
  cidr_block = var.private_subnet_cidrs[count.index]
  availability_zone = tolist(data.aws_availability_zones.available.names)[count.index]

  tags = {
    Name = "smartshop-private-subnet-${count.index + 1}"
  }
}

# Create an Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "smartshop-igw"
  }
}

# Create a Route Table for the Public Subnets
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "smartshop-public-rt"
  }
}

# Associate the Public Route Table with the Public Subnets
resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Get available availability zones
data "aws_availability_zones" "available" {
  state = "available"
}