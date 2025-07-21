
# ==============================================================================
# Backend ECS Service
# ==============================================================================
# This service runs and maintains the desired number of instances of the
# backend task definition.
resource "aws_ecs_service" "backend" {
  name            = "smartshop-backend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1 # Start with one instance of the backend
  launch_type     = "FARGATE"

  # Configure the network to place our task in the private subnets.
  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.private_sg.id]
  }

  service_registries {
    registry_arn = aws_service_discovery_service.backend.arn
  }

  # Connect the service to our Application Load Balancer so it can
  # receive traffic.
  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "smartshop-backend"
    container_port   = 8000
  }

  # This depends_on block ensures that the ALB listener rule is created
  # before this service tries to attach to it.
  depends_on = [aws_lb_listener_rule.backend]
}


# ==============================================================================
# Frontend ECS Service
# ==============================================================================
# This service runs and maintains the desired number of instances of the
# frontend task definition.
resource "aws_ecs_service" "frontend" {
  name            = "smartshop-frontend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1 # Start with one instance of the frontend
  launch_type     = "FARGATE"

  network_configuration {
    subnets         = aws_subnet.private[*].id
    security_groups = [aws_security_group.private_sg.id]
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.frontend.arn
    container_name   = "smartshop-frontend"
    container_port   = 80
  }

  depends_on = [aws_lb_listener_rule.frontend]
}