import requests

from decouple import config


def get_session(session, auth_data):
    if session is None:
        if auth_data is None:
            auth_data = get_auth_data()
        session = requests.session()
    if auth_data is not None:
        session.auth = auth_data
    return session


def get_auth_data(env_username='PP_USER', env_password='PP_PASSWORD'):
    username = config(env_username)
    pw = config(env_password)
    auth_data = (username, pw)
    assert username and pw
    return auth_data


def subdict(fromdict, fields, default=None,  force=False):
    """
    Return a dictionary with the specified selection of keys from `fromdict`.
    If `default` is not None or `force` is true, set missing requested keys to
    the value of `default`.
    (Argument `force` is only needed if the desired default is None)
    """
    if default is not None:
        force = True
    return { k: fromdict.get(k, default) for k in fields if k in fromdict or force }


def check_status_and_raise(response, logger=None, data=None, log_text=False):
    """
    Call the raise_for_status() method of the response, which will
    raise an HTTPError if an error response was received.
    But enrich it with information from our API, and also log
    the call parameters to module_logger.

    :param response: `requests` response object
    :param data: dictionary of call parameters, to include in log
    :param log_text: If true, add the content of `response.text` to the log
    :return: None
    """

    # Nothing to do on success
    if response.status_code == requests.codes.ok:
        return None

    method = response.request.method
    target_url = response.request.url

    content = response.json()

    # Our JSON error messages are labelled inconsistently:
    # "errorMessage" for Extractor bad arguments?
    message = content.get("errorMessage", "")
    # "responseBase -> message" for "Concept Index is empty" == no extraction model
    if not message and "responseBase" in content:
        message = content["responseBase"].get("message", "")

    if message:
        extra = "API error message: {}\n".format(message)
    else:
        extra = None

    # Log the error
    logged = 'URL of the failed {} request: {}\n'.format(method, target_url)

    if data:
        logged += 'JSON data of the failed {} request: {}\n'.format(method, data)

    # GraphSearch logging includes the `text` field:
    if log_text and getattr(response, "text"):
        logged += 'Response text: {}'.format(response.text)

    # Add error details from json envelope, if we found any
    if extra:
        logged += extra

    # Log it all
    if logger:
        logger.error(logged)

    # If we have a message to add, capture and enrich the exception
    if extra:
        try:
            response.raise_for_status()
        except Exception as e:
            raise type(e)(str(e) + "\n" + extra)
    else:
        response.raise_for_status()
