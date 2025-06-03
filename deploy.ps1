$env:DOCKER_BUILDKIT = "0"

$image     = 'lambda/crypto-bot'
$accountId = '654654340294'
$region    = 'eu-north-1'
$registry  = "$accountId.dkr.ecr.$region.amazonaws.com"
$repoUri   = "$registry/$image"
$imageUri = "$repoUri" + ":latest"

aws ecr get-login-password --region $region |
    docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE) { exit 1 }

docker build -t "$repoUri" .
if ($LASTEXITCODE) { exit 1 }

docker push "$repoUri"
if ($LASTEXITCODE) { exit 1 }

aws lambda update-function-code --function-name "$functionName" --image-uri "$imageUri" --region "$region"
if ($LASTEXITCODE) { exit 1 }

# Invoke Lambda function
$outputFile = "output.json"
aws lambda invoke --function-name $functionName --region $region --payload '{}' $outputFile --cli-binary-format raw-in-base64-out
if ($LASTEXITCODE) { exit 1 }

Get-Content $outputFile