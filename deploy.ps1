$env:DOCKER_BUILDKIT = "0"

$image     = 'lambda/crypto-bot'
$accountId = '654654340294'
$region    = 'eu-north-1'
$registry  = "$accountId.dkr.ecr.$region.amazonaws.com"
$repoUri   = "$registry/$image"
$imageUri = "$repoUri" + ":latest"
$functionName = "bot-trade-crypto"

aws ecr get-login-password --region $region |
    docker login --username AWS --password-stdin $registry
if ($LASTEXITCODE) { exit 1 }

docker build -t "$repoUri" .
if ($LASTEXITCODE) { exit 1 }

docker push "$repoUri"
if ($LASTEXITCODE) { exit 1 }

aws lambda update-function-code --function-name "$functionName" --image-uri "$imageUri" --region "$region"
if ($LASTEXITCODE) { exit 1 }