from __future__ import absolute_import

import opentracing
import opentracing.ext.tags as ext
import wrapt

from ..log import logger
from ..singletons import agent, tracer
from ..util import id_to_header

try:
    import flask

    def before_request_with_instana(*argv, **kwargs):
        try:
            if not agent.can_send():
                return

            rc = flask._request_ctx_stack.top
            env = rc.request.environ
            ctx = None

            if 'HTTP_X_INSTANA_T' in env and 'HTTP_X_INSTANA_S' in env:
                ctx = tracer.extract(opentracing.Format.HTTP_HEADERS, env)

            rc.g.scope = tracer.start_active_span('wsgi', child_of=ctx)
            span = rc.g.scope.span

            if agent.extra_headers is not None:
                for custom_header in agent.extra_headers:
                    # Headers are available in this format: HTTP_X_CAPTURE_THIS
                    header = ('HTTP_' + custom_header.upper()).replace('-', '_')
                    if header in env:
                        span.set_tag("http.%s" % custom_header, env[header])

            span.set_tag(ext.HTTP_METHOD, rc.request.method)
            if 'PATH_INFO' in env:
                span.set_tag(ext.HTTP_URL, env['PATH_INFO'])
            if 'QUERY_STRING' in env and len(env['QUERY_STRING']):
                span.set_tag("http.params", env['QUERY_STRING'])
            if 'HTTP_HOST' in env:
                span.set_tag("http.host", env['HTTP_HOST'])
        except:
            logger.debug("Flask before_request", exc_info=True)
        finally:
            return None

    def after_request_with_instana(response):
        try:
            rc = flask._request_ctx_stack.top

            # If we're not tracing, just return
            if not hasattr(rc.g, 'scope'):
                return response

            scope = rc.g.scope
            span = scope.span

            if 500 <= response.status_code <= 511:
                span.set_tag("error", True)
                ec = span.tags.get('ec', 0)
                if ec is 0:
                    span.set_tag("ec", ec+1)

            span.set_tag(ext.HTTP_STATUS_CODE, int(response.status_code))
            response.headers.add('HTTP_X_INSTANA_T', id_to_header(span.context.trace_id))
            response.headers.add('HTTP_X_INSTANA_S', id_to_header(span.context.span_id))
            response.headers.add('HTTP_X_INSTANA_L', 1)
        except:
            logger.debug("Flask after_request", exc_info=True)
        finally:
            if scope is not None:
                scope.close()
            return response

    @wrapt.patch_function_wrapper('flask', 'templating._render')
    def render_with_instana(wrapped, instance, argv, kwargs):
        ctx = argv[1]

        # If we're not tracing, just return
        if not hasattr(ctx['g'], 'scope'):
            return wrapped(*argv, **kwargs)

        with tracer.start_active_span("render", child_of=ctx['g'].scope.span) as rscope:
            try:
                template = argv[0]

                rscope.span.set_tag("type", "template")
                if template.name is None:
                    rscope.span.set_tag("name", '(from string)')
                else:
                    rscope.span.set_tag("name", template.name)
                return wrapped(*argv, **kwargs)
            except Exception as e:
                rscope.span.log_exception(e)
                raise

    @wrapt.patch_function_wrapper('flask', 'Flask.full_dispatch_request')
    def full_dispatch_request_with_instana(wrapped, instance, argv, kwargs):
        if not hasattr(instance, '_stan_wuz_here'):
            logger.debug("Applying flask before/after instrumentation funcs")
            setattr(instance, "_stan_wuz_here", True)
            instance.after_request(after_request_with_instana)
            instance.before_request(before_request_with_instana)
        return wrapped(*argv, **kwargs)

    logger.debug("Instrumenting flask")
except ImportError:
    pass