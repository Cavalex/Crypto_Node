import json
import hashlib
import time

import time

from json_canonical import canonicalize

import jsonschema

from utility.json_validation import *
from utility.logplus import LogPlus
from utility.credentials_utility import *

from object.CoinbaseTransaction import CoinbaseTransaction
from object.Transaction import Transaction

from engine.MessageGenerator import MessageGenerator

from config import *
from json_keys import *

from database.ObjectHandler import *
from database.UTXO import UTXO, TransactionsInvalidException

from network.NodeNetworking import *

from utility.Exceptions import ValidationException, MissingDataException

class Block:

    def __init__(self, txids, nonce, miner, note, previd, created, t):
        self.txids = txids
        self.nonce = nonce
        self.miner = miner
        self.note = note
        self.previd = previd
        self.created = created
        self.t = t

    def get_json(self):
        block_json = {
            type_key: "block",
            "txids": self.txids,
            "nonce": self.nonce,
            "miner": self.miner,
            "note": self.note,
            "previd": self.previd,
            "created": self.created,
            "T": self.t
        }
        return block_json

    def get_id(self):
        block_json = self.get_json()
        canonical_block_json = canonicalize(block_json)
        blockid = hashlib.sha256(canonical_block_json).hexdigest()
        return blockid
    
    def get_type(self):
        return "block" 

    @staticmethod
    def from_json(block_json):
        #jsonschema.validate(block_json, block_schema)
        try:
            jsonschema.validate(block_json, block_schema)
        except jsonschema.exceptions.ValidationError as e:
            LogPlus.error("| ERROR | Block.from_json | " + str(e))
            return None
        block = Block(
            block_json[txids_key],
            block_json[nonce_key],
            block_json[miner_key],
            block_json[note_key],
            block_json[previd_key],
            block_json[created_key],
            block_json[T_key]
        )
        return block

    def verify(self):
        """
        - ??? Create logic to represent a block ??? 2022-11-24
        - ??? Check that the block contains all required fields and that they are of the format specified
        - ??? Ensure the target is the one required, i.e. `00000002af000000000000000000000000000000000000000000000000000000`
        - ??? Check the proof-of-work.
        - ??? Check that for all the txids in the block, you have the corresponding transaction in your local object database. If not, then send a `getobject` message to your peers in order to get the transaction.
        - ??? For each transaction in the block, check that the transaction is valid, and update your UTXO set based on the transaction. More details on this in Exercise B:. If any transaction is invalid, the whole block will be considered invalid.
        - ??? Check for coinbase transactions. There can be at most one coinbase transaction in a block. If present, then the txid of the coinbase transaction must be at index 0 in txids. The coinbase transaction cannot be spent in another transaction in the same block.
        - ??? Validate the coinbase transaction if there is one.
        - ??? Check that the coinbase transaction has no inputs, exactly one output and a height. Check that the height and the public key are of the valid format.
        - ??? Verify the law of conservation for the coinbase transaction. The output of the coinbase transaction can be at most the sum of transaction fees in the block plus the block reward. In our protocol, the block reward is a constant 50 ?? 1012 picaker. The fee of a transaction is the sum of its input values minus the sum of its output values.
        - ??? When you receive a block object from the network, validate it. If valid, then store the block in your local database and gossip the block.
        """

        missing_data = []
        pending_prev = []

        # First part of verification
        try:
            self.verify_proof_of_work()
            self.check_note_and_miner_text()
            # from check_previous_block we get a json containing a list of missing objects and 
            prev_block_status = self.check_previous_block()
            if prev_block_status == "missing":
                missing_data.append(self.previd)
            elif prev_block_status == "pending":
                pending_prev.append(self.previd)
            elif prev_block_status == "invalid":
                raise ValidationException("Invalid previous block")
            missing_data += self.check_transactions_weak()
            # Log the height
            height = self.get_height()
            if height != -1:
                LogPlus.debug(f"| DEBUG | Block.verify | Height: {height}")
        except ValidationException as e:
            LogPlus.info(f"| INFO | Block.verify part 1 failed | {e}")
            return {"result": "invalid"}
        except Exception as e:
            LogPlus.error(f"| ERROR | Block.verify | A | Exception: {e}")
            return {"result": "invalid"}

        if len(missing_data) is not 0 or len(pending_prev) is not 0:
            return {"result": "pending", "missing": missing_data, "pending": pending_prev}

        # Second part of verification
        try:
            self.check_coinbase_transaction()
            self.check_height()
            self.check_created_timestamp()
            self.check_fees()
            self.check_transactions_strong()

        except ValidationException as e:
            LogPlus.info(f"| INFO | Block.verify part 2 failed | {e}")
            return {"result": "invalid"}
        except MissingDataException as e:
            # This should never happen, because we already checked for missing data
            # But if it does, the block still shouldn't be considered invalid
            LogPlus.error(f"| ERROR | Block.verify | MissingDataException: {e}")
            return {"result": "pending", "missing": [], "pending": [self.previd]}
        except Exception as e:
            LogPlus.error(f"| ERROR | Block.verify | B | Exception: {e}")
            return {"result": "invalid"} 

        return { "result": "valid" }

    def verify_proof_of_work(self):
        """ Check that the target is the one required and that the proof-of-work is valid.
        Raise ValidationException if not valid."""
        # Ensure the target is the one required
        if self.t != TARGET:
            LogPlus.info("| INFO | Block.verify_proof_of_work | Target is not the one required")
            raise ValidationException("Target is not the one required")
        
        # Check the proof-of-work: blockid < target
        blockid = self.get_id()
        if int(blockid, 16) >= TARGET_INT:
            LogPlus.info("| INFO | Block.verify_proof_of_work | Proof-of-work is not valid")
            raise ValidationException("Proof-of-work is not valid")


    def check_previous_block(self):
        """Check for previous block.
        Returning "valid", "pending" or "missing" depending on the status of the previous block.
        Raises ValidationException if the previous block is invalid. """

        # check if its valid, pending or invalid
        if ObjectHandler.get_status(self.previd) == "invalid":
            LogPlus.info("| INFO | Block.check_previous_block | Previous block is invalid")
            raise ValidationException("Previous block is invalid")
        elif ObjectHandler.get_status(self.previd) == "pending":
            LogPlus.info("| INFO | Block.check_previous_block | Previous block is pending")
            return "pending"
        elif ObjectHandler.get_status(self.previd) == "valid":
            LogPlus.info("| INFO | Block.check_previous_block | Previous block is valid")
            return "valid"
        else:
            LogPlus.info("| INFO | Block.check_previous_block | Previous block is not found")
            return "missing"

    
    def check_transactions_weak(self):
        """Check if all included transactions are known and valid
        If unknown, return the ids of the transactions to be missing
        If invalid, raise ValidationException"""
        missing_data = []

        for txid in self.txids:
            if ObjectHandler.get_object(txid) is None:
                missing_data.append(txid)
            elif ObjectHandler.get_status(txid) == "invalid":
                # Actual validity check is done in the next step
                # This is just to check if the transaction is known and invalid
                # It could be valid here, but invalid in the next step when it is checked against the UTXO set
                raise ValidationException(f"Included transaction with id {txid} is invalid")

        return missing_data

    def check_coinbase_transaction(self):
        """ Check if the first transaction is a coinbase transaction
        Raises ValidationException if not """
        if len(self.txids) == 0:
            raise ValidationException("No transactions in block")
        first_txid = self.txids[0]
        first_tx_json = ObjectHandler.get_object(first_txid)
        try:
            jsonschema.validate(first_tx_json, coinbase_transaction_schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ValidationException(f"First transaction is not a coinbase transaction")

        # TODO: Check if the coinbase transaction is valid


    def check_height(self):
        """ Check if the height is correct
        Raises ValidationException if not"""
        # Check if prev block is the genesis block
        height = self.get_height()

        if height == 1: # This means that the previous block is the genesis block
            if self.previd != GENESIS_BLOCK_ID:
                raise ValidationException("The previous block is not the genesis block, but height is 1")
            return

        # Check if the height is correct
        prev_block_json = ObjectHandler.get_object(self.previd)
        prev_coinbase_tx_json = ObjectHandler.get_object(prev_block_json[txids_key][0])
        prev_height = prev_coinbase_tx_json[height_key]

        if height != prev_height + 1:
            raise ValidationException("The height is not correct")

    def check_created_timestamp(self):
        """ Check if the created timestamp is correct
        Raises ValidationException if not"""
        
        # Check if it's after now
        if self.created > time.time():
            raise ValidationException("The created timestamp is in the future")

        # Check if it's before the previous block
        prev_block_json = ObjectHandler.get_object(self.previd)
        if self.created < prev_block_json[created_key]: # TODO: Check if < or <= is correct
            raise ValidationException("The created timestamp is before the previous block")

    def check_transactions_strong(self):
        """ Check if all transactions are valid
        This is done by checking the UTXO set
        Raises ValidationException if not valid"""
        try:
            # try calculating the UTXO set
            # this will raise an exception if the UTXO set is not valid
            # if the utxo set is valid, all transactions are valid
            UTXO.calculate_set(self.get_json())
        except TransactionsInvalidException as e:
            raise ValidationException(f"Transactions are not valid: {e}")

        
    def check_fees(self):
        """ Check if coinbase vale is correct
        tx fees + block reward >= coinbase transaction value
        Raises ValidationException if not valid"""
        # sum up tx fees
        tx_fees = 0
        for txid in self.txids[1:]:
            tx_json = ObjectHandler.get_object(txid)
            tx = Transaction.from_json(tx_json)
            tx_fees += tx.get_fee()

        coinbase_txid = self.txids[0]
        coinbase_tx_json = ObjectHandler.get_object(coinbase_txid)
        coinbase_tx_value = coinbase_tx_json[outputs_key][0][value_key]

        # tx fees + block reward >= coinbase transaction value
        if tx_fees + BLOCK_REWARD < coinbase_tx_value:
            LogPlus.info(f"| INFO | Block.verify | The coinbase transaction value is not valid")
            raise ValidationException("The coinbase transaction value is not valid")

    def check_note_and_miner_text(self):
        """Ensure that the note and miner fields in a block are ASCII-printable strings up to 128 characters long each. 
        ASCII printable characters are those with decimal values 32 up to 126."""
        if not self.note.isascii() or not self.miner.isascii():
            raise ValidationException("The note or miner fields are not ASCII printable")
        if len(self.note) > 128 or len(self.miner) > 128:
            raise ValidationException("The note or miner fields are longer than 128 characters")

    def get_height(self):
        """ Get the height of the block
        Returns -1 if the block is coinbase transaction is not found"""
        try:
            coinbase_txid = self.txids[0]
            coinbase_tx_json = ObjectHandler.get_object(coinbase_txid)
            if coinbase_tx_json is None:
                return -1
            return coinbase_tx_json[height_key]
        except Exception as e:
            LogPlus.error(f"| ERROR | Block.get_height | {e}")
            return -1
