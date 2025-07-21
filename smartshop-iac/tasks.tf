
# ==============================================================================
# IAM Role for ECS Tasks
# ==============================================================================
# This role grants the ECS tasks permission to be executed by AWS services
# and to pull images from ECR.
resource "aws_iam_role" "ecs_task_execution_role" {
  name = "ecs_task_execution_role"

  assume_role_policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [
      {
        Action    = "sts:AssumeRole",
        Effect    = "Allow",
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# Attach the standard AWS managed policy for ECS task execution.
resource "aws_iam_role_policy_attachment" "ecs_task_execution_role_policy" {
  role       = aws_iam_role.ecs_task_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}


# ==============================================================================
# Backend Service Task Definition
# ==============================================================================
resource "aws_ecs_task_definition" "backend" {
  family                   = "smartshop-backend-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024" # 1 vCPU
  memory                   = "2048" # 2 GB
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  # This is the blueprint for the container itself.
  container_definitions = jsonencode([
    {
      name      = "smartshop-backend"
      image     = aws_ecr_repository.backend.repository_url
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
        }
      ]
      # Pass environment variables to the container.
      # We use the outputs from our RDS and ElastiCache resources.
      environment = [
        {
            name  = "PYTHONPATH",
            value = "/app"
        },
        {
            name  = "VECTOR_DB_HOST",
            value = "vector_db.smartshop.local"
        },
        {
          name  = "DATABASE_URL",
          value = "postgresql://${var.db_user}:${var.db_password}@${aws_db_instance.main.address}/${aws_db_instance.main.db_name}"
        },
        {
          name  = "REDIS_URL",
          value = "redis://${aws_elasticache_cluster.main.cache_nodes[0].address}:${aws_elasticache_cluster.main.cache_nodes[0].port}"
        }
        # Add other non-sensitive environment variables here if needed
      ]
      # Configure logging to send container output to CloudWatch.
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/smartshop-backend"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# ==============================================================================
# Frontend Service Task Definition
# ==============================================================================
resource "aws_ecs_task_definition" "frontend" {
  family                   = "smartshop-frontend-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"  # 0.25 vCPU
  memory                   = "512"  # 0.5 GB
  execution_role_arn       = aws_iam_role.ecs_task_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "smartshop-frontend"
      image     = aws_ecr_repository.frontend.repository_url
      essential = true
      portMappings = [
        {
          containerPort = 80
          hostPort      = 80
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = "/ecs/smartshop-frontend"
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

# Create the CloudWatch log groups for our tasks
resource "aws_cloudwatch_log_group" "backend_logs" {
  name = "/ecs/smartshop-backend"
}

resource "aws_cloudwatch_log_group" "frontend_logs" {
  name = "/ecs/smartshop-frontend"
}