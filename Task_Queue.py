from queue import *
from threading import Thread
import time
import random

class Task:
    def __init__(self, target, args):
        self.target = target
        self.args = args

def thread_checker(q):
    while not q.empty():
        next_task = q.get()
        #print('starting ' + str(next_task.args))
        next_task.target(*next_task.args)
        q.task_done()
    return

def full_run(task_list, thread_num=32):
    thread_num = min(len(task_list), thread_num)
    q = Queue(maxsize=-1)
    for each_task in task_list:
        q.put(each_task)

    for count in range(thread_num):
        next_thread = Thread(target=thread_checker, args=[q], daemon=False)
        next_thread.start()
        print(next_thread)
    q.join()