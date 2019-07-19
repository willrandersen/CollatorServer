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
            print('starting task')
            task_in_thread = Thread(target=next_task.target, args=next_task.args)
            running_threads.append(task_in_thread)
            task_in_thread.start()
        for each_thread in running_threads:
            if not each_thread.isAlive():
                running_threads.remove(each_thread)