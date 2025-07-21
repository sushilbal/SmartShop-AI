# Create a private DNS namespace for service discovery.
# This will allow services to find each other using DNS names
# like "backend.smartshop.local".
resource "aws_service_discovery_private_dns_namespace" "main" {
  name        = "smartshop.local"
  description = "Private DNS namespace for the SmartShop application"
  vpc         = aws_vpc.main.id
}

resource "aws_service_discovery_service" "backend" {
  name = "backend"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records {
      ttl  = 10
      type = "A"
    }
    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}