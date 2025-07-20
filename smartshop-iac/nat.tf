# Create an Elastic IP for the NAT Gateway
resource "aws_eip" "nat" {
  domain = "vpc"
  tags = {
    Name = "smartshop-nat-eip"
  }
}

# Create a NAT Gateway in the first public subnet
resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "smartshop-nat-gw"
  }

  # Ensure the Internet Gateway is created before the NAT Gateway
  depends_on = [aws_internet_gateway.main]
}

# Create a Route Table for the Private Subnets
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Name = "smartshop-private-rt"
  }
}

# Associate the Private Route Table with the Private Subnets
resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}