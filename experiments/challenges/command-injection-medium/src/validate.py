#!/usr/bin/env python3

import re

'''
This file implements a class Validator
with a function that checks whether a string
contains some denylisted characters (`, $, ...)
'''


class Validator:
    def __init__(self, denylist):
        self.denylist = denylist
        self.protectlist = ['shutdown', 'poweroff', 'reboot']

    def validate(self, string):
        for c in self.denylist:
            if c in string:
                return False
        return True
    
    def protect(self, string):
        '''
        Checks for disruption attempts
        such as shutdown, poweroff, reboot, ...
        '''
        for c in self.protectlist:
            if c in string.lower():
                return c
        return None
