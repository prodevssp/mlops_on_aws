provider "aws" {
  region = "us-east-1"
}
data "aws_caller_identity" "current" {}

locals {
  project_name = "ml-code"
}

locals {
  function_name = "main_lambda"
}

resource "aws_codecommit_repository" "source" {
  repository_name = "${local.project_name}-repo"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.project_name}-artifacts-dbs"
}

# Create an S3 bucket to store the Lambda function deployment package
resource "aws_s3_bucket" "lambda_bucket" {
  bucket = "lambda-code-dbs"
}

# Create the IAM role for the Lambda function
resource "aws_iam_role" "lambda_role" {
  name = "${local.function_name}_execution_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Create the IAM policy for the Lambda function
resource "aws_iam_policy" "lambda_policy" {
  name        = "${local.function_name}_policy"
  description = "IAM policy for ${local.function_name} Lambda function"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Effect   = "Allow"
        Resource = "*"
      }
    ]
  })
}

# Attach the IAM policy to the IAM role
resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  policy_arn = aws_iam_policy.lambda_policy.arn
  role       = aws_iam_role.lambda_role.name
}

# Automatically zip the lambda code
data "archive_file" "main_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda_functions/main_lambda.py"
  output_path = "${path.module}/lambda_functions/main_lambda.zip"
}
# Main lambda to control the flow
resource "aws_lambda_function" "main_lambda" {
  function_name = local.function_name
  role          = aws_iam_role.lambda_role.arn
  handler       = "main_lambda.lambda_handler"
  filename      = data.archive_file.main_lambda_zip.output_path
  timeout = 60
  runtime = "python3.8"
  environment {
    variables = {
      OWNER = "Soumya"
    }
  }
}

resource "aws_codepipeline" "pipeline" {
  name     = "${local.project_name}-pipeline"
  role_arn = aws_iam_role.pipeline_role.arn

  artifact_store {
    location = aws_s3_bucket.artifacts.bucket
    type     = "S3"
  }

  stage {
    name = "Source"

    action {
      name             = "Source"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeCommit"
      version          = "1"
      output_artifacts = ["source_output"]

      configuration = {
        RepositoryName = aws_codecommit_repository.source.repository_name
        BranchName     = "master"
      }
    }
  }

  stage {
    name = "Build"

    action {
      name             = "Build"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      input_artifacts  = ["source_output"]
      output_artifacts = ["build_output"]
      version          = "1"

      configuration = {
        ProjectName = aws_codebuild_project.build_project.name
      }
    }
  }
}

resource "aws_iam_role" "pipeline_role" {
  name = "codepipeline-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "codepipeline.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "pipeline_s3_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
  role       = aws_iam_role.pipeline_role.name
}

resource "aws_iam_role_policy_attachment" "pipeline_codebuild_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AWSCodeBuildAdminAccess"
  role       = aws_iam_role.pipeline_role.name
}

resource "aws_ecr_repository" "repository" {
  name = "${local.project_name}-repository"
}

resource "aws_codebuild_project" "build_project" {
  name          = "${local.project_name}-build"
  description   = "Build project for ${local.project_name}"
  service_role  = aws_iam_role.codebuild_role.arn
  build_timeout = "5"
  
  artifacts {
    type = "CODEPIPELINE"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = true
    image_pull_credentials_type = "CODEBUILD"
    environment_variable {
      name  = "REPOSITORY_URI"
      value = "${aws_ecr_repository.repository.repository_url}"
    }
  }

  source {
    type      = "CODEPIPELINE"
    buildspec = "buildspec.yml"
  }
}

resource "aws_iam_role" "codebuild_role" {
  name = "codebuild-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
        Service = "codebuild.amazonaws.com"
            }
        }]
    })
}

resource "aws_iam_policy" "codebuild_ecr_policy" {
  name        = "codebuild-ecr-policy"
  description = "Policy granting required ECR permissions for CodeBuild"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:GetRepositoryPolicy",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = "*"
      }
    ]
  })
}




resource "aws_iam_policy" "codebuild_lambda_policy"{
  name        = "codebuild-lambda-policy"
  description = "Policy granting required Lambda permissions for CodeBuild"
  policy = jsonencode({
  Version = "2012-10-17"
  Statement = [
    {
      Action = "lambda:InvokeFunction"
      Effect = "Allow"
      Resource = aws_lambda_function.main_lambda.arn
    }
  ]
})
}


resource "aws_iam_role_policy_attachment" "codebuild_ecr_policy" {
  policy_arn = aws_iam_policy.codebuild_ecr_policy.arn
  role       = aws_iam_role.codebuild_role.name
}

resource "aws_iam_role_policy_attachment" "codebuild_lambda_policy" {
  policy_arn = aws_iam_policy.codebuild_lambda_policy.arn
  role       = aws_iam_role.codebuild_role.name
}



resource "aws_iam_role_policy_attachment" "pipeline_codecommit_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AWSCodeCommitFullAccess"
  role       = aws_iam_role.pipeline_role.name
}

resource "aws_iam_role_policy_attachment" "codebuild_s3_policy" {
policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
role = aws_iam_role.codebuild_role.name
}

resource "aws_iam_role_policy_attachment" "codebuild_logs_policy" {
policy_arn = "arn:aws:iam::aws:policy/CloudWatchLogsFullAccess"
role = aws_iam_role.codebuild_role.name
}

resource "aws_s3_bucket" "source" {
bucket = "${local.project_name}-source-dbs"
}

output "codepipeline_arn" {
value = aws_codepipeline.pipeline.arn
}

output "codebuild_project_arn" {
value = aws_codebuild_project.build_project.arn
}

# CT 
locals {
  lambda_function_name = "ec2_launcher"
}

data "archive_file" "ec2_launcher_zip" {
  type        = "zip"
  source_file = "${path.module}/lambda_functions/launch_ec2.py"
  output_path = "${path.module}/lambda_functions/launch_ec2.zip"
}

resource "aws_lambda_function" "ec2_launcher" {
  function_name = local.lambda_function_name
  handler       = "launch_ec2.lambda_handler"
  runtime       = "python3.8" 
  timeout       = 60
  role = aws_iam_role.ec2_lambda_role.arn
  filename = data.archive_file.ec2_launcher_zip.output_path
  source_code_hash = filebase64sha256(data.archive_file.ec2_launcher_zip.output_path)
}

resource "aws_iam_role" "ec2_lambda_role" {
  name = "ec2_lambda_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "create_role" {
  name        = "iam-create-role-policy"
  description = "Policy granting lambda to create roles"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "iam:*"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "iam_create_role_ec2_lambda" {
  policy_arn = aws_iam_policy.create_role.arn
  role       = aws_iam_role.ec2_lambda_role.name
}

resource "aws_iam_role_policy_attachment" "lambda_policy" {
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
  role       = aws_iam_role.ec2_lambda_role.name
}

resource "aws_iam_role_policy_attachment" "lambda_ec2_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2FullAccess"
  role       = aws_iam_role.ec2_lambda_role.name
}

resource "aws_iam_role" "sfn_orchestrator_role" {
  name = "sfn_orchestrator_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "sfn_policy" {
  policy_arn = "arn:aws:iam::aws:policy/AWSStepFunctionsFullAccess"
  role       = aws_iam_role.sfn_orchestrator_role.name
}

resource "aws_sfn_state_machine" "invoke_lambda" {
  name     = "ml-pipeline-orchestrator"
  role_arn = aws_iam_role.sfn_orchestrator_role.arn

  definition = jsonencode({
    Comment = "EC2 lanucher lambda function"
    StartAt = "Start_EC2"
    States = {
      Start_EC2 = {
        Type     = "Task"
        Resource = aws_lambda_function.ec2_launcher.arn
        Next      = "Training_Model"
      },
      Training_Model = {
        Type= "Wait",
        Seconds= 180,
        End: true
    },
    }
  })
}

resource "aws_iam_policy" "sfn_lambda_invoke" {
  name        = "sfn_lambda_invoke"
  description = "Allow Step Functions to invoke Lambda functions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "lambda:InvokeFunction"
        Effect = "Allow"
        Resource = aws_lambda_function.ec2_launcher.arn
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "sfn_lambda_invoke_attachment" {
  policy_arn = aws_iam_policy.sfn_lambda_invoke.arn
  role       = aws_iam_role.sfn_orchestrator_role.name
}

output "ec2_arn" {
value = aws_lambda_function.ec2_launcher.arn
}
