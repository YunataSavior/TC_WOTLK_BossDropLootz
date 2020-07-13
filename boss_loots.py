import argparse
import os
import socket
import sys
import mysql.connector as cnct

# GLOBALS:
mySqlIp = "127.0.0.1"
root_pwd = ""
sql_port = 3306

# DEBUG:
debugCommit = True

def connect_to_db():
    dbCnct = cnct.connect(
        #connect_timeout=3,
        host=mySqlIp,
        port=sql_port,
        user="root",
        passwd=root_pwd,
        db="world"
    )
    return dbCnct

def perform_query(dbCnct, mode):
    query = ("SELECT Entry,Item,Chance,GroupId FROM {}_loot_template "
             "WHERE Reference=0 AND QuestRequired=0 AND GroupId != 0;".format(mode))
    myCursor = dbCnct.cursor()
    myCursor.execute(query)
    #dbCnct.commit()
    entry_gid_chance_dict = {}

    for (Entry,Item,Chance,GroupId) in myCursor:
        if Entry not in entry_gid_chance_dict:
            entry_gid_chance_dict[Entry] = {}
        if GroupId not in entry_gid_chance_dict[Entry]:
            entry_gid_chance_dict[Entry][GroupId] = Chance
        else:
            entry_gid_chance_dict[Entry][GroupId] += Chance
            # edge case: some ZF/Mara bosses have entries with 0 chance, but other entries in the same GroupIs have non-zero chances,
            #  This translates to: there must always be at least one drop
            if Chance == 0:
                entry_gid_chance_dict[Entry][GroupId] = 100
            if entry_gid_chance_dict[Entry][GroupId] > 100:
                entry_gid_chance_dict[Entry][GroupId] = 100

    entry_to_del = []
    for Entry in entry_gid_chance_dict:
        gid_to_del = []
        for GroupId in entry_gid_chance_dict[Entry]:
            total_chance = entry_gid_chance_dict[Entry][GroupId]
            # Verify that chance is 0 or 100:
            if (total_chance > 0 and total_chance < 99):
                gid_to_del.append(GroupId)
                continue
            # Check that possible items are rare or better:
            local_items = []
            myCursor.execute("SELECT Item FROM {}_loot_template WHERE Entry={} AND GroupId={};".format(mode,Entry,GroupId))
            for (Item,) in myCursor:
                #print(Item)
                local_items.append(Item)
            not_rare = False
            for item in local_items:
                my_q = "SELECT Quality FROM item_template WHERE entry={};".format(item)
                #print(my_q)
                myCursor.execute(my_q)
                for (Quality,) in myCursor:
                    if Quality < 3:
                        not_rare = True
                        break
                if not_rare == True:
                    break
            if not_rare == True:
                gid_to_del.append(GroupId)
                continue
            # Now print:
            name_ = ""
            eEntry = ""
            qType = "UNDEF"
            if mode == "creature":
                qType = "Entry"
            elif mode == "gameobject":
                qType = "data1"
            myCursor.execute("SELECT Entry,name FROM {}_template WHERE {}={};".format(mode,qType,Entry))
            for (eEntry,name,) in myCursor:
                name_ = name
            print("{}({}) {}: {}".format(eEntry, name, GroupId, entry_gid_chance_dict[Entry][GroupId]))
            myCursor.execute("UPDATE {}_loot_template SET Chance=100,GroupId=0 WHERE Entry={} AND GroupId={}".format(mode,Entry,GroupId))
            dbCnct.commit()
        for gid in gid_to_del:
            del entry_gid_chance_dict[Entry][gid]
        if (len(entry_gid_chance_dict[Entry]) == 0):
            entry_to_del.append(Entry)
    for entry in entry_to_del:
        del entry_gid_chance_dict[entry]

    myCursor.close()
    return dbCnct
    
# -------------------------------------------------------------------------------------------------------------------------------------------------------------

# CONDITION 1: Trivial case: All items are rare, and all have a chance to be rolled on

def check_cond1(myCursor, Reference):
    query = ("SELECT Entry,Reference,Item,Chance,GroupId FROM reference_loot_template "
             "WHERE Entry={};".format(Reference))
    myCursor.execute(query)
    inner_results = []
    for (Entry,iReference,Item,Chance,GroupId) in myCursor:
        inner_results.append((Entry,iReference,Item,Chance,GroupId))
    for (Entry,iReference,Item,Chance,GroupId) in inner_results:
        if iReference != 0 or Chance != 100 or GroupId != 0:
            return (myCursor, False)
    return (myCursor, True)

def try_apply_cond1(dbCnct, myCursor, Reference):
    query = ("SELECT Entry,Reference,Item,Chance,GroupId FROM reference_loot_template "
             "WHERE Entry={};".format(Reference))
    myCursor.execute(query)
    inner_results = []
    for (Entry,iReference,Item,Chance,GroupId) in myCursor:
        inner_results.append((Entry,iReference,Item,Chance,GroupId))
    for (Entry,iReference,Item,Chance,GroupId) in inner_results:
        # 1st, Check no sub-references:
        if iReference != 0:
            return (dbCnct, myCursor, False)
    query = ("UPDATE reference_loot_template SET Chance=100,GroupId=0"
             " WHERE Entry={};".format(Reference))
    #print(query)
    myCursor.execute(query)
    for mode in ["reference", "creature", "gameobject"]:
        query = ("UPDATE {}_loot_template SET Chance=100,GroupId=0,MinCount=1,MaxCount=1"
                 " WHERE Reference={};".format(mode, Reference))
        #print(query)
        myCursor.execute(query)
    dbCnct.commit()
    return (dbCnct, myCursor, True)

# ~~~~~~~~~~~~~~~~~~~~

# CONDITION 2: Some WOTLK dungeon bosses have their full drop tables in reference_loot_template, rather than creature_loot_template

# precondition: cond1 doesn't hold
def check_cond2(myCursor, Reference):
    query = ("SELECT Entry,Reference,Item,Chance,GroupId FROM reference_loot_template "
             "WHERE Entry={};".format(Reference))
    myCursor.execute(query)
    inner_results = []
    for (Entry,iReference,Item,Chance,GroupId) in myCursor:
        inner_results.append((Entry,iReference,Item,Chance,GroupId))
    for (Entry,iReference,Item,Chance,GroupId) in inner_results:
        if iReference != 0 or GroupId != 0:
            return (myCursor, False)
    return (myCursor, True)

def try_apply_cond2(dbCnct, myCursor, Reference):
    query = ("SELECT Entry,Reference,Item,Chance,GroupId FROM reference_loot_template "
             "WHERE Entry={};".format(Reference))
    myCursor.execute(query)
    inner_results = []
    for (Entry,iReference,Item,Chance,GroupId) in myCursor:
        inner_results.append((Entry,iReference,Item,Chance,GroupId))
    for (Entry,iReference,Item,Chance,GroupId) in inner_results:
        # 1st, Check no sub-references:
        if iReference != 0:
            return (dbCnct, myCursor, False)
    query = ("UPDATE reference_loot_template SET Chance=100,GroupId=0"
             " WHERE Entry={} AND GroupId != 0;".format(Reference))
    #print(query)
    myCursor.execute(query)
    dbCnct.commit()
    return (dbCnct, myCursor, True)

# ++++++++++++++++++++++++++++++++++++++

# depth is a debug variable; doesn't affect anything
#  (I found the max to be 2)
# Returns: (myCursor, # of rare+ items, # of non-rare+ items)
def recursive_references(myCursor, Reference, depth=1):
    num_basic = 0
    num_rare = 0
    query = ("SELECT Entry,Reference,Item,Chance,GroupId FROM reference_loot_template "
             "WHERE Entry={};".format(Reference))
    myCursor.execute(query)
    inner_results = []
    for (Entry,Reference,Item,Chance,GroupId) in myCursor:
        inner_results.append((Entry,Reference,Item,Chance,GroupId))
    for (Entry,Reference,Item,Chance,GroupId) in inner_results:
        if (Reference != 0):
            myCursor, tnum_rare, tnum_basic = recursive_references(myCursor, Reference, depth+1)
            num_rare += tnum_rare
            num_basic += tnum_basic
            #print("NESTED {}".format(depth))
        else:
            myCursor.execute("SELECT name,Quality FROM item_template WHERE entry={};".format(Item))
            for (name,Quality) in myCursor:
                if Quality < 3:
                    num_basic += 1
                else:
                    num_rare += 1
    return (myCursor, num_rare, num_basic)
    
def boost_drops_with_ref_templ(dbCnct, mode):
    gid_only = ""
    #gid_only = "AND GroupId != 0"
    myCursor = dbCnct.cursor()
    query = ("SELECT Entry,Reference,MinCount,MaxCount,GroupId FROM {}_loot_template "
             "WHERE Reference != 0 {} AND QuestRequired=0 AND Chance=100;".format(mode,gid_only))
    myCursor.execute(query)
    results = []
    parsed_refs = []
    for (Entry,Reference,MinCount,MaxCount,GroupId) in myCursor:
        results.append((Entry,Reference,MinCount,MaxCount,GroupId))
    # Ent,Ref: outer loop
    for (Ent,Ref,Min,Max,Gid) in results:
        if Ref in parsed_refs:
            continue
        myCursor, num_rare, num_basic = recursive_references(myCursor, Ref)
        if (num_rare == 0):
            continue
        if (num_basic >= 10):
            continue
        # check condition:
        has_cond = False
        myCursor, has_cond = check_cond1(myCursor, Ref)
        if has_cond == True:
            continue
        myCursor, has_cond = check_cond2(myCursor, Ref)
        if has_cond == True:
            continue
        # apply condition:
        if (num_basic == 0):
            dbCnct, myCursor, has_cond = try_apply_cond1(dbCnct, myCursor, Ref)
        if (has_cond == False):
            dbCnct, myCursor, has_cond = try_apply_cond2(dbCnct, myCursor, Ref)
        # Now print:
        name_ = ""
        eEntry = ""
        qType = "UNDEF"
        if mode == "creature":
            qType = "Entry"
        elif mode == "gameobject":
            qType = "data1"
        myCursor.execute("SELECT Entry,name FROM {}_template WHERE {}={};".format(mode,qType,Ent))
        for (eEntry,name,) in myCursor:
            name_ = name
        if (len(name_) == 0):
            continue
        print("[Gid={},Min={},Max={}] Entry={}({}) Ref={}: rare={}, basic={}".format(Gid,Min,Max,eEntry,name_,Ref, num_rare, num_basic))
        parsed_refs.append(Ref)
        
    myCursor.close()
    return dbCnct
    
# -------------------------------------------------------------------------------------------------------------------------------------------------------------

# some bosses don't always drop unique blues; sometimes they do
# (e.g. Doctor Zul'mah in Zul'Farrak)
# These cases MUST be hardcoded, otherwise all loot will become spammy:
def hardcoded_alterations(dbCnct):
    myCursor = dbCnct.cursor()
    # Doctor Zul'mah in Zul'Farrak
    query = ("UPDATE creature_loot_template SET Chance=100,GroupId=0"
             " WHERE Entry=7271 AND GroupId=1;")
    print(query)
    myCursor.execute(query)
    dbCnct.commit()
    myCursor.close()
    return dbCnct

# -------------------------------------------------------------------------------------------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Modify WotLK TrinityCore Lootz.")
    #parser.add_argument("mySqlIp", type=str, help="IP Addr of the MySQL database.")
    #args = parser.parse_args()
    #mySqlIp = args.mySqlIp
    try:
        pwd_fd = open("root_pwd.txt", 'r')
        root_pwd = pwd_fd.read()
        root_pwd = root_pwd.split("\n")[0]
        pwd_fd.close()
    except FileNotFoundError:
        print("ERROR: password file \"root_pwd.txt\" non existent. Please create this file in the same directory as "
              "this Python script file, then put your MySQL root password in there")
        sys.exit()
    try:
        port_fd = open("sql_port.txt", 'r')
        sSQL = port_fd.read()
        sql_port = int(sSQL.split("\n")[0])
        port_fd.close()
    except FileNotFoundError:
        print("ERROR: Please create a file in the same directory as this Python script file named \"sql_port.txt\", "
              "then put your MySQL port in there. It should be 3306, but it your actual port may differ...")
        sys.exit()
    except ValueError:
        print("ERROR: \"sql_port.txt\" contains an invalid string. It must be a valid number")
        sys.exit()
    try:
        dbCnct = connect_to_db()
    except cnct.errors.ProgrammingError:
        print("Connection failed. Is password in \"root_pwd.txt\" bad?")
        sys.exit()

    print("=== creature ===")
    dbCnct = perform_query(dbCnct, "creature")
    print("----------------")
    dbCnct = boost_drops_with_ref_templ(dbCnct, "creature")
    print("=== gameobject ===")
    dbCnct = perform_query(dbCnct, "gameobject")
    print("----------------")
    dbCnct = boost_drops_with_ref_templ(dbCnct, "gameobject")
    print("=== other ===")
    dbCnct = hardcoded_alterations(dbCnct)
    
    dbCnct.close()
