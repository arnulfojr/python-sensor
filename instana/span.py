from basictracer.span import BasicSpan


class InstanaSpan(BasicSpan):
    stack = None

    def finish(self, finish_time=None):
        super(InstanaSpan, self).finish(finish_time)

    def log_exception(self, e, as_tag=False):
        if hasattr(e, 'message') and len(e.message):
            error_message = e.message
        elif hasattr(e, '__str__'):
            error_message = e.__str__()
        else:
            error_message = str(e)

        if as_tag:
            self.set_tag('message', error_message)
        else:
            self.log_kv({'message': error_message})

        self.set_tag("error", True)
        ec = self.tags.get('ec', 0)
        self.set_tag("ec", ec+1)
