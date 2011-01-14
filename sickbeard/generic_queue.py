# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import operator
import threading
import Queue
import traceback

import sickbeard
from sickbeard import logger

class QueuePriorities:
    LOW = 30
    NORMAL = 20
    HIGH = 10

class GenericQueue(object):

    def __init__(self):

        self.currentItem = None
        self.queue = []

        self.thread = None

        self.queue_name = "QUEUE"

        self.min_priority = 0
        
        self.currentItem = None

    def pause(self):
        logger.log(u"Pausing queue")
        self.min_priority = 999999999999
    
    def unpause(self):
        logger.log(u"Unpausing queue")
        self.min_priority = 0

    def add_item(self, item):
        self.queue.append(item)

    def run(self):

        # only start a new task if one isn't already going
        if self.thread == None or self.thread.isAlive() == False:

            # if the thread is dead then the current item should be finished
            if self.currentItem != None:
                self.currentItem.finish()
                self.currentItem = None

            # if there's something in the queue then run it in a thread and take it out of the queue
            if len(self.queue) > 0:

                # sort by priority
                self.queue.sort(key=operator.attrgetter('priority'))
                
                queueItem = self.queue[0]

                if queueItem.priority < self.min_priority:
                    return

                # launch the queue item in a thread
                # TODO: improve thread name
                threadName = self.queue_name + '-' + queueItem.get_thread_name()
                self.thread = threading.Thread(None, queueItem.execute, threadName)
                self.thread.start()

                self.currentItem = queueItem

                # take it out of the queue
                del self.queue[0]

class QueueItem:
    def __init__(self, name, action_id = 0):
        self.name = name

        self.inProgress = False

        self.priority = QueuePriorities.NORMAL

        self.thread_name = None

        self.action_id = action_id

    def get_thread_name(self):
        if self.thread_name:
            return self.thread_name
        else:
            return self.name.replace(" ","-").upper()

    def execute(self):
        """Implementing classes should call this"""

        self.inProgress = True

    def finish(self):
        """Implementing Classes should call this"""

        self.inProgress = False

class GenericTaskQueue(object):
    def __init__(self, number_of_workers):
        self.queue = Queue.PriorityQueue()
        self.queue_allow_running = threading.Event()
        self.init_queue_threadpool(number_of_workers)
        self.start_queue_workers()
        self.current_items = [None for _ in range(number_of_workers)]
        
    def _get_action(self):
        return self

    action = property(_get_action)

    def _worker_entry_point(self, id, queue):
        while True:
            self.queue_allow_running.wait(None)
            if not self.queue_allow_running.is_set():
                return
                
            try:
                priority, item = self.queue.get(True, 2)
                try:
                    self.current_items[id] = item
                    item.run()
                except:
                    logger.crit(traceback.format_exc())

                self.current_items[id] = None

            except Queue.Empty:
                # the queue was empty - nothing to schedule - just ignore
                pass

    def abort(self):
        self.queue_allow_running.clear()

    def init_queue_threadpool(self, number):
        self.queue_allow_running.set()
        self.queue_threadpool = [
                threading.Thread(None, self._worker_entry_point, "Queue worker %i" % (id,), (id, self.queue))
                for id in range(number)]

    def start_queue_workers(self):
        for thread in self.queue_threadpool:
            thread.start()

    def add_item(self, item):
        if not hasattr(item, run):
            raise Exception("Submitted item is not runnable")

        if isinstance(item, QueueItem):
            self.queue.put((item.priority, item))
        else:
            self.queue.put((QueuePriorities.NORMAL, item))

    def get_current_queue(self):
        """This way is not thread-safe at all - the result should be only informative"""

        return self.current_items + self.queue.queue

    def get_queue_iterator(self):
        for _prio, x in self.queue.queue:
            yield x

    def join(self, timeout):
        for th in self.queue_threadpool:
            th.join(timeout)

