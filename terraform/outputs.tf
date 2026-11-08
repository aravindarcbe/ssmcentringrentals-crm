output "public_ip" {
  description = "Elastic IP address — point your domain's DNS A record here."
  value       = aws_eip.app.public_ip
}

output "instance_id" {
  value = aws_instance.app.id
}

output "ssh_command" {
  value = "ssh -i /path/to/${var.key_name}.pem ubuntu@${aws_eip.app.public_ip}"
}
