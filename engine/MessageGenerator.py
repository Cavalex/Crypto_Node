import json

from config import *
from json_keys import *


class MessageGenerator:

    @staticmethod
    def generate_hello_message():
        message_json = {type_key: hello_key, version_key: "0.8.0", agent_key: AGENT_NAME}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_getpeers_message():
        message_json = {type_key: getpeers_key}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_peers_message(peers):
        message_json = {type_key: peers_key, peers_key: peers}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_error_message(error):
        message_json = {type_key: error_key, error_key: error}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def get_bytes_from_json(message_json):
        return str.encode(json.dumps(message_json) + "\n")

    @staticmethod
    def generate_ihaveobject_message(object_id):
        message_json = {type_key: ihaveobject_key, objectid_key: object_id}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_getobject_message(object_id):
        message_json = {type_key: getobject_key, objectid_key: object_id}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_object_message(object_data):
        message_json = {type_key: object_key, object_key: object_data}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_getchaintip_message():
        message_json = {type_key: getchaintip_key}
        return MessageGenerator.get_bytes_from_json(message_json)

    @staticmethod
    def generate_chaintip_message(block_id):
        message_json = {type_key: chaintip_key , blockid_key: block_id}
        return MessageGenerator.get_bytes_from_json(message_json)

    # TODO : Mempool messages
