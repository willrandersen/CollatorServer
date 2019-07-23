# from queue import *
# from threading import Thread
# import time
# import random
#
# class Task:
#     def __init__(self, target, args):
#         self.target = target
#         self.args = args
#
# def thread_checker(q):
#     while not q.empty():
#         next_task = q.get()
#         #print('starting ' + str(next_task.args))
#         next_task.target(*next_task.args)
#         q.task_done()
#     return
#
# def full_run(task_list, thread_num=32):
#     thread_num = min(len(task_list), thread_num)
#     q = Queue(maxsize=-1)
#     for each_task in task_list:
#         q.put(each_task)
#
#     for count in range(thread_num):
#         next_thread = Thread(target=thread_checker, args=[q], daemon=False)
#         next_thread.start()
#         print(next_thread)
#     q.join()


from queue import *
from threading import Thread


class Task:
    def __init__(self, target, args):
        self.target = target
        self.args = args


def full_run(task_list, thread_num=256):
    thread_num = min(thread_num, len(task_list))

    task_queue = Queue(maxsize=-1)
    for each_task in task_list:
        task_queue.put(each_task)

    running_threads = []
    while not task_queue.empty() or len(running_threads) > 0:
        while len(running_threads) < thread_num and not task_queue.empty():
            next_task = task_queue.get()
            #print('starting task')
            task_in_thread = Thread(target=next_task.target, args=next_task.args)
            running_threads.append(task_in_thread)
            task_in_thread.start()
        for each_thread in running_threads:
            if not each_thread.isAlive():
                running_threads.remove(each_thread)