FROM public.ecr.aws/lambda/python:3.10

COPY app/ ${LAMBDA_TASK_ROOT}/

COPY requirements.txt .
RUN pip install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Patch the kucoin client (example: setting `True` to `False`)
RUN sed -i 's/self._get("fills", False/self._get("fills", True/' ${LAMBDA_TASK_ROOT}/kucoin/async_client.py
RUN sed -i 's/self._get("fills", False/self._get("fills", True/' ${LAMBDA_TASK_ROOT}/kucoin/client.py

# Update the default yaml_path in settings.py
RUN find ${LAMBDA_TASK_ROOT} -name settings.py

CMD ["lambda_function.lambda_handler"]