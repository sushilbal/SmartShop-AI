# Create an Application Load Balancer
resource "aws_lb" "main" {
  name               = "smartshop-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.public_sg.id]
  subnets            = aws_subnet.public[*].id

  enable_deletion_protection = false

  tags = {
    Name = "smartshop-alb"
  }
}

# Create a default Target Group for the ALB.
# This will be used by the frontend service.
resource "aws_lb_target_group" "frontend" {
  name        = "smartshop-frontend-tg"
  port        = 80 # The frontend container listens on port 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

# Create a Listener for the ALB to forward HTTP traffic
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}