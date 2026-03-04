variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes version for the node group"
  type        = string
}

variable "node_instance_type" {
  description = "EC2 instance type for worker nodes"
  type        = string
}

variable "node_min_count" {
  description = "Minimum number of nodes"
  type        = number
}

variable "node_max_count" {
  description = "Maximum number of nodes"
  type        = number
}

variable "node_desired_count" {
  description = "Desired number of nodes"
  type        = number
}

variable "subnet_ids" {
  description = "Subnets for the node group"
  type        = list(string)
}

variable "tags" {
  description = "Tags to apply to node group resources"
  type        = map(string)
}

resource "aws_iam_role" "node_group" {
  name = "${var.cluster_name}-nodegroup-role"

  assume_role_policy = data.aws_iam_policy_document.nodegroup_assume_role.json

  tags = var.tags
}

data "aws_iam_policy_document" "nodegroup_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy_attachment" "worker_node" {
  role       = aws_iam_role.node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "cni" {
  role       = aws_iam_role.node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "ecr_read_only" {
  role       = aws_iam_role.node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_eks_node_group" "this" {
  cluster_name    = var.cluster_name
  node_group_name = "${var.cluster_name}-node-group"
  node_role_arn   = aws_iam_role.node_group.arn
  subnet_ids      = var.subnet_ids

  scaling_config {
    min_size     = var.node_min_count
    max_size     = var.node_max_count
    desired_size = var.node_desired_count
  }

  instance_types = [var.node_instance_type]

  tags = var.tags
}

