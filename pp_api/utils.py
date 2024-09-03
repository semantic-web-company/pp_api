import requests
from json import JSONDecodeError

import simplejson

from decouple import config
from oauthlib.oauth2 import LegacyApplicationClient
from requests_oauthlib import OAuth2Session
from time import time

saved_token = None

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


def get_oauth_session(session, auth_data):
    def token_saver(token):
        pass

    if session is None:
        if auth_data is None:
            auth_data = get_auth_data_oauth2()
    # fetch the initial token
    session = OAuth2Session(client=LegacyApplicationClient(client_id=auth_data.client_id))
    token = session.fetch_token(token_url=auth_data.token_url,
                      username=auth_data.username, password=auth_data.password, client_id=auth_data.client_id,
                      client_secret=auth_data.client_secret)
    # set up the automatic refresh workflow
    token["expires_at"] = time() - 10
    session = OAuth2Session(client=LegacyApplicationClient(client_id=auth_data.client_id), client_id=auth_data.client_id, token=token, auto_refresh_url=auth_data.token_url, auto_refresh_kwargs=auth_data.__dict__, token_updater=token_saver)
    return session


class OAuthConfiguration:
    def __init__(self, username, password, client_id, client_secret, token_url):
        self.username = username
        self.password = password
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url


def get_auth_data_oauth2(env_username='PP_USER', env_password='PP_PASSWORD', env_client_id='PP_CLIENT_ID', env_cliebt_secret='PP_CLIENT_SECRET', env_toke_url='PP_TOKEN_URL'):
    username = config(env_username)
    pw = config(env_password)
    client_id = config(env_client_id)
    client_secret = config(env_cliebt_secret)
    token_url = config(env_toke_url)
    oauth_configuration = OAuthConfiguration(username, pw, client_id, client_secret, token_url)
    return oauth_configuration


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
    if response.status_code < 299:
        return None

    method = response.request.method
    target_url = response.request.url

    # json() chokes on empty response text, so bypass it
    if response.text:
        try:
            content = response.json()
        except simplejson.errors.JSONDecodeError:
            # Sometimes the error message is not json at all, but html;
            # just wrap it for the benefit of later code
            content = { "errorMessage": response.text }
    else:
        content = {}

    # Our JSON error messages are labelled inconsistently:
    # "errorMessage" for Extractor bad arguments?
    # "message" for add_custom_relation failure
    message = content.get("errorMessage", "") or content.get("message", "")
    # "responseBase -> message" for "Concept Index is empty" == no extraction model
    if not message and "responseBase" in content:
        message = content["responseBase"].get("message", "")

    # response.reason seems to be already included in the exception

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
            with_extra = e.args[0] + "\n" + extra
            e.args = (with_extra,) + e.args[1:]
            # Re-raise the current exception
            raise
    else:
        response.raise_for_status()
