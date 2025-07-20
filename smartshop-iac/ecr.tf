# ecr.tf

# Create an ECR repository for the Backend service
resource "aws_ecr_repository" "backend" {
  name = "smartshop-backend"
  
  tags = {
    Name = "smartshop-backend"
  }
}

# Create an ECR repository for the Frontend service
resource "aws_ecr_repository" "frontend" {
  name = "smartshop-frontend"
  
  tags = {
    Name = "smartshop-frontend"
  }
}

# Create an ECR repository for the Embedding Model service
resource "aws_ecr_repository" "embedding_model" {
  name = "smartshop-embedding-model"
  
  tags = {
    Name = "smartshop-embedding-model"
  }
}

# Create an ECR repository for the Vector DB service
resource "aws_ecr_repository" "vector_db" {
  name = "smartshop-vector-db"

  tags = {
    Name = "smartshop-vector-db"
  }
}