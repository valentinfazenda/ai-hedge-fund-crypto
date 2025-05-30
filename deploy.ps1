$env:DOCKER_BUILDKIT = "0"

$imageName = "lambda/crypto-bot"
$awsAccountId = "654654340294"
$region = "eu-north-1"
$ecrRepo = "$awsAccountId.dkr.ecr.$region.amazonaws.com/$imageName"

aws ecr get-login-password --region $region | docker login --username AWS --password-stdin "$awsAccountId.dkr.ecr.$region.amazonaws.com"

docker build -t $imageName .
docker tag "$imageName:latest" "$ecrRepo:latest"
docker push "$ecrRepo:latest"