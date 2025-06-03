FROM public.ecr.aws/lambda/python:3.10

COPY app/ ${LAMBDA_TASK_ROOT}/

COPY requirements.txt .
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Replace "app/config.yaml" with "config.yaml" in settings.py
RUN find ${LAMBDA_TASK_ROOT} -name settings.py -exec sed -i 's|"app/config.yaml"|"config.yaml"|g' {} \;

CMD ["lambda_function.lambda_handler"]