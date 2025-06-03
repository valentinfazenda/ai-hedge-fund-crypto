FROM public.ecr.aws/lambda/python:3.10

COPY app/ ${LAMBDA_TASK_ROOT}/

COPY requirements.txt .
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Update the default yaml_path in settings.py
RUN find ${LAMBDA_TASK_ROOT} -name settings.py

CMD ["lambda_function.lambda_handler"]