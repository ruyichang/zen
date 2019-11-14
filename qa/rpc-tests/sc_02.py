#!/usr/bin/env python2
# Copyright (c) 2014 The Bitcoin Core developers
# Copyright (c) 2018 The Zencash developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
from test_framework.test_framework import BitcoinTestFramework
from test_framework.authproxy import JSONRPCException
from test_framework.util import assert_equal, assert_false, assert_true, initialize_chain_clean, \
    start_nodes, start_node, connect_nodes, stop_node, stop_nodes, \
    sync_blocks, sync_mempools, connect_nodes_bi, wait_bitcoinds, p2p_port, check_json_precision
import traceback
import os,sys
import shutil
from random import randint
from decimal import Decimal
import logging
import time

NUMB_OF_NODES = 3

class headers(BitcoinTestFramework):

    alert_filename = None

    def setup_chain(self, split=False):
        print("Initializing test directory "+self.options.tmpdir)
        initialize_chain_clean(self.options.tmpdir, NUMB_OF_NODES)
        self.alert_filename = os.path.join(self.options.tmpdir, "alert.txt")
        with open(self.alert_filename, 'w'):
            pass  # Just open then close to create zero-length file

    def setup_network(self, split=False):
        self.nodes = []

        self.nodes = start_nodes(NUMB_OF_NODES, self.options.tmpdir,
            extra_args=[['-sccoinsmaturity=0', '-logtimemicros=1', '-debug=sc', '-debug=py', '-debug=mempool', '-debug=net', '-debug=bench']] * NUMB_OF_NODES )

        if not split:
            # 1 and 2 are joint only if split==false
            connect_nodes_bi(self.nodes, 1, 2)
            sync_blocks(self.nodes[1:NUMB_OF_NODES])
            sync_mempools(self.nodes[1:NUMB_OF_NODES])

        connect_nodes_bi(self.nodes, 0, 1)
        self.is_network_split = split
        self.sync_all()

    def disconnect_nodes(self, from_connection, node_num):
        ip_port = "127.0.0.1:"+str(p2p_port(node_num))
        from_connection.disconnectnode(ip_port)
        # poll until version handshake complete to avoid race conditions
        # with transaction relaying
        while any(peer['version'] == 0 for peer in from_connection.getpeerinfo()):
            time.sleep(0.1)

    def split_network(self):
        # Split the network of three nodes into nodes 0-1 and 2.
        assert not self.is_network_split
        self.disconnect_nodes(self.nodes[1], 2)
        self.disconnect_nodes(self.nodes[2], 1)
        self.is_network_split = True

    def join_network(self):
        #Join the (previously split) network pieces together: 0-1-2
        assert self.is_network_split
        connect_nodes_bi(self.nodes, 1, 2)
        connect_nodes_bi(self.nodes, 2, 1)
        #self.sync_all()
        time.sleep(2)
        self.is_network_split = False

    def dump_ordered_tips(self, tip_list):
        sorted_x = sorted(tip_list, key=lambda k: k['status'])
        c = 0
        for y in sorted_x:
            if (c == 0):
                print y 
            else:
                print " ",y 
            c = 1

    def dump_sc_info_record (self, info, i):
        print "  Node %d - balance: %f" % ( i, info["balance"])
        print "    created in block: %s (%d)" % (info["created in block"], info["created at block height"])
        print "    created in tx:    %s" % info["creating tx hash"]

    def dump_sc_info(self, scId=""):
        if scId != "":
            print "scid: %s" % scId
            print "-------------------------------------------------------------------------------------"
            for i in range(0, NUMB_OF_NODES):
                try:
                    self.dump_sc_info_record( self.nodes[i].getscinfo(scId), i )
                except JSONRPCException,e:
                    print "  Node %d: ### [no such scid: %s]" % (i, scId)
        else:
            for i in range(0, NUMB_OF_NODES):
                x = self.nodes[i].getscinfo()
                for info in x:
                    self.dump_sc_info_record( info, i)
        print


    def mark_logs(self, msg):
        print msg
        self.nodes[0].dbg_log(msg)
        self.nodes[1].dbg_log(msg)
        self.nodes[2].dbg_log(msg)

    def run_test(self):

        ''' This test creates a Sidechain and forwards funds to it and then verifies
          that scinfo is updated correctly in active chain also after blocks rollback
          and alternative fork propagations
        '''
        # network topology: (0)--(1)--(2)
        blocks = []
        self.bl_count = 0

        blocks.append(self.nodes[0].getblockhash(0))

        # node 1 earns some coins, they would be available after 100 blocks 
        self.mark_logs("Node 1 generates 1 block")
        blocks.extend(self.nodes[1].generate(1))
        self.sync_all()

        self.mark_logs("Node 0 generates 220 block")
        blocks.extend(self.nodes[0].generate(220))
        self.sync_all()
        pre_sc_block = blocks[-1]

        print "\n############ Node1 balance: ", self.nodes[1].getbalance("", 0)

        # side chain id
        scid = "22"

        creation_amount = Decimal("1.0")
        fwt_amount_1 = Decimal("1.0")
        fwt_amount_2 = Decimal("2.0")
        fwt_amount_3 = Decimal("3.0")
        fwt_amount_many = fwt_amount_1 + fwt_amount_2 + fwt_amount_3

        #---------------------------------------------------------------------------------------
        self.mark_logs("\nNode 1 creates SC")
        amounts = []
        amounts.append( {"address":"dada", "amount": creation_amount})
        creating_tx_2 = self.nodes[1].sc_create(scid, 123, amounts);
        print "tx=" + creating_tx_2
        self.sync_all()

        self.mark_logs("\n...Node0 generating 1 block")
        blocks.extend(self.nodes[0].generate(1))
        ownerBlock = blocks[-1]
        self.sync_all()

        self.mark_logs("\nNode 1 sends "+str(fwt_amount_1)+" coins to SC")
        tx = self.nodes[1].sc_send("abcd", fwt_amount_1, scid);
        print "tx=" + tx
        self.sync_all()

        self.mark_logs("\nNode 1 sends "+str(fwt_amount_1)+" coins to SC")
        tx = self.nodes[1].sc_send("abcd", fwt_amount_1, scid);
        print "tx=" + tx
        self.sync_all()

        self.mark_logs("\n...Node0 generating 1 block")
        blocks.extend(self.nodes[0].generate(1))
        self.sync_all()

        self.mark_logs("\nNode 1 sends 3 amounts to SC (tot: "+str(fwt_amount_many) + ")")
        amounts = []
        amounts.append( {"address":"add1", "amount": fwt_amount_1, "scid": scid})
        amounts.append( {"address":"add2", "amount": fwt_amount_2, "scid": scid})
        amounts.append( {"address":"add3", "amount": fwt_amount_3, "scid": scid})
        tx = self.nodes[1].sc_sendmany(amounts);
        print "tx=" + tx
        self.sync_all()

        print("\n...Node0 generating 1 block")
        blocks.extend(self.nodes[0].generate(1))
        self.sync_all()

        print "\n############ Node1 balance: ", self.nodes[1].getbalance("", 0)

        print "\nChecking SC info on network..."
        print
        self.dump_sc_info(scid)

        assert_equal(self.nodes[2].getscinfo(scid)["balance"], creation_amount + 2*fwt_amount_1 + fwt_amount_many) 
        assert_equal(self.nodes[2].getscinfo(scid)["created in block"], ownerBlock) 
        assert_equal(self.nodes[2].getscinfo(scid)["creating tx hash"], creating_tx_2) 

        print "\nChecking network chain tips..."
        print 
        for i in range(0, NUMB_OF_NODES):
            self.dump_ordered_tips(self.nodes[i].getchaintips())
            print "---"

        # node 2 invalidates the block just before the SC creation thus originating a chain fork
        self.mark_logs("\nNode 2 invalidates the pre-SC block..")

        raw_input("Press to invalidate block...")
        try:
            self.nodes[2].invalidateblock(pre_sc_block);
        except JSONRPCException,e:
            errorString = e.error['message']
            print errorString

        #self.sync_all()
        time.sleep(2)

        print "\nChecking network chain tips, Node 2 has a shorter fork..."
        print 
        for i in range(0, NUMB_OF_NODES):
            self.dump_ordered_tips(self.nodes[i].getchaintips())
            print "---"

        # Node2 mempool will contain all the transactions from the blocks reverted
        print "\nChecking mempools, Node 2 has the reverted blocks transaction..."
        print "Node 0: ", self.nodes[0].getrawmempool()
        print "Node 1: ", self.nodes[1].getrawmempool()
        print "Node 2: ", self.nodes[2].getrawmempool()

        print "\nChecking SC info on the whole network, Node 2 should not have any SC..."
        self.dump_sc_info(scid)

        # the SC is recretaed on the Node2 forked chain with all the balance
        self.mark_logs("\n...Node 2 generates 3 malicious blocks...")
        blocks.extend(self.nodes[2].generate(3))
        #self.sync_all()
        time.sleep(2)

        print "\nChecking network chain tips, Node 2 propagated the fork to its peer..."
        print 
        for i in range(0, NUMB_OF_NODES):
            self.dump_ordered_tips(self.nodes[i].getchaintips())
            print "---"

        info_node_0 = self.nodes[0].getscinfo(scid)
        info_node_1 = self.nodes[1].getscinfo(scid)
        info_node_2 = self.nodes[2].getscinfo(scid)

        assert_true(info_node_0 == info_node_1)
        assert_false(info_node_0 == info_node_2)

        print "\nChecking that SC belongs to different blocks on the different forks..."
        print
        self.dump_sc_info(scid)

        # try to forward coins to the sc, each node has its own SC info data
        self.mark_logs("\nNode 1 sends "+str(fwt_amount_1)+" coins to SC")
        tx_after_fork = self.nodes[1].sc_send("abcd", fwt_amount_1, scid);
        print "tx=" + tx_after_fork
        #self.sync_all()
        time.sleep(2)

        # the SC balance will be updated only in the node 2 forked chain 
        self.mark_logs("\n...Node 2 generates 1 malicious blocks, its chain will have the same length as the honest...")
        blocks.extend(self.nodes[2].generate(1))
        #self.sync_all()
        time.sleep(2)

        print "\nChecking SC info on the whole network, balance is updated only in Node2 fork..."
        self.dump_sc_info(scid)

        print "\nChecking network chain tips, Node 2 fork has reached the length of the honest fork..."
        print 
        for i in range(0, NUMB_OF_NODES):
            self.dump_ordered_tips(self.nodes[i].getchaintips())
            print "---"

        # on the other nodes the tx will remain in the mempool
        print "\nChecking mempools, Node 0 and 1 still have last tx in the mempool..."
        print "Node 0: ", self.nodes[0].getrawmempool()
        print "Node 1: ", self.nodes[1].getrawmempool()
        print "Node 2: ", self.nodes[2].getrawmempool()

        #raw_input("press enter to go on..")

        # node0/1 will update the SC on their forked chain, including the tx in a different block than Node 2
        print("\n...Node0 generating 1 block")
        blocks.extend(self.nodes[0].generate(1))
        #self.sync_all()
        time.sleep(2)

        print "\nChecking SC info on the whole network, balance is now updated everywhere..."
        self.dump_sc_info(scid)

        # check that the forks will have the same tx in different blocks
        tx_0_block = self.nodes[0].getrawtransaction(tx_after_fork, 1)['blockhash']
        tx_1_block = self.nodes[1].getrawtransaction(tx_after_fork, 1)['blockhash']
        tx_2_block = self.nodes[2].getrawtransaction(tx_after_fork, 1)['blockhash']
        assert_false(tx_0_block == tx_2_block)
        assert_true(tx_0_block == tx_1_block)
        print "\nOk, last tx belongs to different blocks"
        print "  Owner block of last tx on node 0: " + tx_0_block
        print "  Owner block of last tx on node 0: " + tx_1_block
        print "  Owner block of last tx on node 2: " + tx_2_block
        
        self.mark_logs("\nNode 2 generates 2 malicious blocks, its chain will prevail over honest one...")
        blocks.extend(self.nodes[2].generate(2))
        self.sync_all()

        print "\nChecking network chain tips, Node 2 fork has prevailed..."
        print 
        for i in range(0, NUMB_OF_NODES):
            self.dump_ordered_tips(self.nodes[i].getchaintips())
            print "---"

        # the honest chain at node 0/1 has been reverted, all data should now match 
        print "\nChecking SC info on the whole network, all data match..."
        self.dump_sc_info(scid)

        print "\n############ Node1 balance: ", self.nodes[1].getbalance("", 0)
        print "\nChecking SC info on the whole network..."

        info_node_0 = self.nodes[0].getscinfo(scid)
        info_node_1 = self.nodes[1].getscinfo(scid)
        info_node_2 = self.nodes[2].getscinfo(scid)

        assert_equal(info_node_0, info_node_1)
        assert_equal(info_node_1, info_node_2)

        self.dump_sc_info(scid)

        # check tx is contained in the same block
        tx_0_block = self.nodes[0].getrawtransaction(tx_after_fork, 1)['blockhash']
        tx_1_block = self.nodes[1].getrawtransaction(tx_after_fork, 1)['blockhash']
        tx_2_block = self.nodes[2].getrawtransaction(tx_after_fork, 1)['blockhash']
        assert_true(tx_0_block == tx_2_block)
        assert_true(tx_1_block == tx_2_block)
        print "\nOk, last tx belongs to the same block"
        print "  Owner block of last tx on node 0: " + tx_0_block
        print "  Owner block of last tx on node 2: " + tx_2_block


if __name__ == '__main__':
    headers().main()