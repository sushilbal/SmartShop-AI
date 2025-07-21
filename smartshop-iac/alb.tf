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

# ------------------------------------------------------------------------------
# Target Groups
# ------------------------------------------------------------------------------

# A target group for the FRONTEND service
resource "aws_lb_target_group" "frontend" {
  name        = "smartshop-frontend-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

# A target group for the BACKEND service
resource "aws_lb_target_group" "backend" {
  name        = "smartshop-backend-tg"
  port        = 8000 # The backend container listens on port 8000
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/api/health" # A typical health check endpoint for a backend
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

# ------------------------------------------------------------------------------
# Listener and Rules
# ------------------------------------------------------------------------------

# Create a Listener for the ALB to handle incoming HTTP traffic
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = "80"
  protocol          = "HTTP"

  # By default, forward to the frontend. This is a fallback.
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }
}

# A rule to forward API traffic to the BACKEND
resource "aws_lb_listener_rule" "backend" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 100 # Lower number = higher priority

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }

  condition {
    path_pattern {
      values = ["/api/*"] # Any path starting with /api/ goes to the backend
    }
  }
}

# A rule to forward all other traffic to the FRONTEND
# This rule is no longer strictly necessary because of the default_action,
# but it can be useful for explicit clarity.
resource "aws_lb_listener_rule" "frontend" {
  listener_arn = aws_lb_listener.http.arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.frontend.arn
  }

  condition {
    path_pattern {
      values = ["/*"] # All other paths
    }
  }
}