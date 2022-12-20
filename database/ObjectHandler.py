import json
import json_canonical
import hashlib

from colorama import Fore, Style

from utility.logplus import LogPlus
from utility.credentials_utility import *
#from UTXO import *
from object.Object import Object
#from object.ObjectCreator import ObjectCreator

from config import *

from json_keys import *


# This class handles all objects
# Objects can be either transactions or blocks
# The type of the object is stored in the object itself in the type_key field
# structure of a regular transaction:
# {
#     type_key: "transaction",
#     "inputs": [
#         {
#             "outpoint": {
#                 "txid": sha256-hash of previous transaction,
#                 "index": index of output within previous transaction
#             },
#             "sig": signature of the input, created with the private key of the owner of the outpoint
#         }
#     ],
#     "outputs": [
#         {
#             "pubkey": public key of the owner of the recipient,
#             "value": amount of coins, in picaker (1 ker = 10^12 picaker)
#         }
#     ]
# }
#
# structure of a coinbase transaction:
# {
#     type_key: "transaction",
#     "height": height of the block this transaction is in,
#     "outputs": [
#         {
#             "pubkey": public key of the owner of the recipient,
#             "value": amount of coins, in picaker (1 ker = 10^12 picaker)
#         }
#     ]
# }
#
# structure of a block:
# {
#     type_key: "block",
#     "txids": [sha256-hash of all transactions in the block],
#     "nonce": nonce of the block (sha256 format),
#     "previd": sha256-hash of the previous block,
#     "created": timestamp of the block creation,
#     "T": target of the block (sha256 format),
#     "miner": any string up to 128 characters
#     "note": any string up to 128 characters
# }

# The object handler also needs a mapping from id to index in object list / object

class ObjectHandler:
  
    id_to_index = {}
    objects_file = OBJECTS_FILE
    objects = DEFAULT_OBJECTS

    @staticmethod
    def update_id_to_index():
        ObjectHandler.id_to_index = {}
        for i in range(len(ObjectHandler.objects)):
            object_id = ObjectHandler.objects[i][txid_key]
            ObjectHandler.id_to_index[object_id] = i

    @staticmethod
    def add_object(obj, validity="valid", type="unknown", sender_address=None):
        """ Adds an object to the object list and saves it to the objects file 
            obj: the object to add
            validity: the validity of the object (valid, invalid, pending)
            type: the type of the object (transaction, block, unknown)
            sender_address: the address of the sender of the object """
        try:
            # if sender is tuple, convert to string
            if type(sender_address) == tuple:
                sender_address = convert_tuple_to_string(sender_address)
            txid = Object.get_id_from_json(obj)
            ObjectHandler.objects.append({
                "txid": txid,
                "validity": validity,
                object_key: obj,
                type_key: type,
                "missing": [],
                "pending": [],
                sender_key: sender_address
            })
            ObjectHandler.id_to_index[txid] = len(ObjectHandler.objects) - 1
            ObjectHandler.save_objects()
            ObjectHandler.update_id_to_index()
            ObjectHandler.update_pending_objects(txid)

        except Exception as e:
            LogPlus.error("| ERROR | ObjectHandler.add_object | " + str(e))
            return False

    @staticmethod
    def get_object(object_id):
        """ Returns the object with the given id """
        if object_id in ObjectHandler.id_to_index.keys():
            return ObjectHandler.objects[ObjectHandler.id_to_index[object_id]][object_key]
        else:
            return None
    
    @staticmethod
    def get_pending_objects():
        """ Returns all pending objects (objects with validity "pending") """
        return ObjectHandler.get_objects_with_status("pending")

    @staticmethod 
    def get_objects_with_status(status):
        """ Returns all objects with the given status """
        return [obj[object_key] for obj in ObjectHandler.objects if obj["validity"] == status]

    @staticmethod
    def get_status(object_id):
        """ Returns the validity of the object with the given id """
        if object_id in ObjectHandler.id_to_index:
            return ObjectHandler.objects[ObjectHandler.id_to_index[object_id]]["validity"]
        else:
            return None

    @staticmethod
    def update_pending_objects(object_id):
        """ Updates all pending objects that depend on the given object, takes the id of the object as input """
        # get status of object
        status = ObjectHandler.get_status(object_id)
        # check if object is in missing objects and remove the dependency
        for pending in [obj for obj in ObjectHandler.objects if obj["validity"] == "pending"]:
            if "missing" in pending.keys() and object_id in pending["missing"]:
                pending["missing"].remove(object_id)
                ObjectHandler.save_objects()

        if status == "valid":
            for pending in [obj for obj in ObjectHandler.objects if obj["validity"] == "pending"]:
                if "pending" in pending.keys() and object_id in pending["pending"]:
                    pending["pending"] = []

        if status == "invalid":
            # check if object is in pending objects and remove the dependency
            for pending in [obj for obj in ObjectHandler.objects if obj["validity"] == "pending"]:
                if "pending" in pending.keys() and object_id in pending["pending"]:
                    pending["pending"] = []
                    pending["validity"] = "invalid"
                    pending["missing"] = []
                    ObjectHandler.save_objects()


    @staticmethod
    def get_verifiable_objects():
        """ Returns all objects that can be verified (objects with validity "pending" or "received") """
        pending_objects = [obj for obj in ObjectHandler.objects if obj["validity"] == "pending"] 
        pending_objects = [obj for obj in pending_objects if "missing" not in obj.keys() or len(obj["missing"]) == 0]
        pending_objects = [obj for obj in pending_objects if "pending" not in obj.keys() or len(obj["pending"]) == 0]
        pending_objects = [obj[object_key] for obj in pending_objects]
        recevied_objects = ObjectHandler.get_objects_with_status("received")
        return pending_objects + recevied_objects


    @staticmethod
    def update_object_status(object_id, validity, missing=[], pending=[]):
        """ Updates the status (and missing & pending) of the object with the given id """
        if object_id in ObjectHandler.id_to_index:
            index = ObjectHandler.id_to_index[object_id]
            ObjectHandler.objects[index]["validity"] = validity
            ObjectHandler.objects[index]["missing"] = missing
            ObjectHandler.objects[index]["pending"] = pending
            ObjectHandler.save_objects()
            if validity in ["valid", "invalid"]:
                ObjectHandler.update_pending_objects(object_id)  

    @staticmethod
    def get_block_containing_object(object_id):
        """ Returns the id of the block containing the object with the given id
            None if the object is not in a block """
        # get all objects of type block
        blocks = [obj[object_key] for obj in ObjectHandler.objects if obj[type_key] == "block"]
        for block in blocks:
            if object_id in block[txids_key]:
                return Object.get_id_from_json(block)
        return None

    @staticmethod
    def get_chaintip():
        """ Returns the id of the chaintip """
        # get all objects of type block
        blocks = [obj[txid_key] for obj in ObjectHandler.objects if obj[type_key] == "block" and obj["validity"] == "valid"]
        LogPlus.debug(f"| DEBUG | ObjectHandler.get_chaintip |  lenblocks: {len(blocks)}")
        if len(blocks) <= 1:
            return Object.get_id_from_json(GENESIS_BLOCK)
        
        # sort out genesis block
        blocks = [blockid for blockid in blocks if blockid != Object.get_id_from_json(GENESIS_BLOCK)]

        # check height in coinbase transaction, return the blockid with the highest height
        chaintip_id = max(blocks, key=lambda block: ObjectHandler.get_height(block))
        return chaintip_id
        #return max(blocks, key=lambda block: get_block_height(block))[txid_key]

    @staticmethod
    def get_block_height(object_id):
        """ Takes an object id and returns the height of the block containing the object, 
            -1 if the object is not a block or the coinbase transaction is not found """
        try:
            # get block
            block = ObjectHandler.get_object(object_id)
            # get coinbase transaction
            coinbase = block[txids_key][0]
            # return height
            return coinbase[height_key]
        except:
            return -1
        

    @staticmethod
    def is_valid(object_id):
        """ Takes an object id and returns True if the object is valid, False otherwise (might still be pending)"""
        if object_id in ObjectHandler.id_to_index:
            return ObjectHandler.get_status(object_id) == "valid"
        else:
            return False

    @staticmethod
    def is_object_known(object_id):
        """ Takes an object id and returns True if the object is known, False otherwise"""
        return object_id in ObjectHandler.id_to_index.keys()

    # Saving and loading objects from file
    @staticmethod
    def save_objects():
        """ Saves the objects to the file """
        try:
            with open(ObjectHandler.objects_file, "w") as f:
                json.dump(ObjectHandler.objects, f, indent=4)

            f.close()

        except Exception as e:
            LogPlus().error(f"| ERROR | ObjectHandler | save_objects failed | {e}")

    @staticmethod
    def load_objects():
        """ Loads the objects from the file and updates the id_to_index dictionary """
        try:
            with open(ObjectHandler.objects_file, "r") as f:
                ObjectHandler.objects = json.load(f)
            ObjectHandler.update_id_to_index()
        except Exception as e:
            ObjectHandler.objects = DEFAULT_OBJECTS
            ObjectHandler.save_objects()
            LogPlus.error(f"| ERROR | ObjectHandler | load_objects failed | {e}")

    @staticmethod
    def get_height(block_id):
        """ Returns the height of the block with the given id """
        try:
            block_json = ObjectHandler.get_object(block_id)
            coinbase_txid = block_json[txids_key][0]
            coinbase_tx_json = ObjectHandler.get_object(coinbase_txid)
            return coinbase_tx_json[height_key]
        except:
            return -1

    @staticmethod
    def get_orginal_sender(txid):
        """ Returns the original sender address of the transaction with the given id """
        try:
            tx_json = ObjectHandler.get_object(txid)
            if tx_json is not None:
                return tx_json[sender_key]
            else:
                return None
        except Exception as e:
            LogPlus.error(f"| ERROR | ObjectHandler | get_orginal_sender failed | {e}")
            return None