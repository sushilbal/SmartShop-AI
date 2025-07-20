# Create an ECS (Elastic Container Service) Cluster
resource "aws_ecs_cluster" "main" {
  name = "smartshop-cluster"

  tags = {
    Name = "smartshop-ecs-cluster"
  }
}