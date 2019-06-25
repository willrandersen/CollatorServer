import os
CELERY_TASK_SERIALIZER = 'pickle'
BROKER_URL = os.environ.get('REDIS_URL', 'redis://h:pa425d66d3225da47094fb328e38667075e5d3a9cb37ed87f12a493e2cce8e965@ec2-34-233-52-24.compute-1.amazonaws.com:31379')
CELERY_ACCEPT_CONTENT = ['pickle', 'json']
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://h:pa425d66d3225da47094fb328e38667075e5d3a9cb37ed87f12a493e2cce8e965@ec2-34-233-52-24.compute-1.amazonaws.com:31379')
BROKER_POOL_LIMIT = 0