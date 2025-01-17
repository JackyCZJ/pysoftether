import base64
from softether.sha0 import sha0Hash

import requests
import json
import urllib3
import datetime
from softether.errors import ERRORS


def sha0(data):
    sha = sha0Hash()
    sha.update(data)
    return sha

def _left_rotate(x, n):
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def from_utf(message):
    raw = ''
    i = 0
    while i < len(message):
        char_code = ord(message[i])
        if char_code < 0x80:
            raw += chr(char_code)
        elif char_code < 0x800:
            raw += chr(0xc0 | (char_code >> 6))
            raw += chr(0x80 | (char_code & 0x3f))
        elif char_code < 0xd800 or char_code >= 0xe000:
            raw += chr(0xe0 | (char_code >> 12))
            raw += chr(0x80 | ((char_code >> 6) & 0x3f))
            raw += chr(0x80 | (char_code & 0x3f))
        else:
            i += 1
            char_code = 0x10000 + (((char_code & 0x3ff) << 10) | (ord(message[i]) & 0x3ff))
            raw += chr(0xf0 | (char_code >> 18))
            raw += chr(0x80 | ((char_code >> 12) & 0x3f))
            raw += chr(0x80 | ((char_code >> 6) & 0x3f))
            raw += chr(0x80 | (char_code & 0x3f))
        i += 1
    return raw


def serialize(data):
    new_data = {}
    for key in data:
        if data[key][1] is None or data[key][1] == [None]:
            continue
        value = data[key][1][0]
        if data[key][0] == "string":
            new_data[key + "_str"] = value
        elif data[key][0] == "int":
            if isinstance(data[key][1], bool):
                new_data[key + "_bool"] = bool(value)
            else:
                new_data[key + "_u32"] = value
        elif data[key][0] == "bool":
            new_data[key + "_bool"] = value
        elif data[key][0] == "raw":
            new_data[key + "_bin"] = value
        elif data[key][0] == "ustring":
            new_data[key + "_utf"] = value
        elif data[key][0] == "int64":
            new_data[key + "_int64"] = value
        elif data[key][0] == "uint64":
            new_data[key + "_u64"] = value
        elif data[key][0] == "datetime":
            new_data[key + "_dt"] = (datetime.datetime.fromtimestamp(value)
                                     .isoformat(timespec='milliseconds'))
        else:
            raise Exception("Unknown type")
    return new_data


class SoftEtherAPIException(Exception):
    pass


class SoftEtherAPIConnector(object):
    host = None
    port = None
    password = None
    hub = None
    suffix = None
    verify = True

    def __init__(self, host, port, password, suffix, hub=None, verify=True):
        self.host = host
        self.port = port
        self.password = password
        self.hub = hub
        self.suffix = suffix
        self.verify = verify

    def send_http_request(self, body, headers=None):
        if headers is None:
            headers = {}
        headers = {
            'Content-Type': 'application/json; charset=utf-8',
            "Access-Control-Allow-Credentials": "true",
            "X-VPNADMIN-HUBNAME": self.hub is None and "administrator" or self.hub,
            "X-VPNADMIN-PASSWORD": self.password,
        }
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        try:
            response = requests.post(self.host + ":" + str(self.port) + self.suffix,
                                     headers=headers, data=json.dumps(body), verify=self.verify)
            return response.json()
        except Exception as e:
            raise SoftEtherAPIException(e)


def key_beautify(data):
    new_data = {}
    for key in data:
        new_data[key.split("_", 1)[0]] = data[key]
        if type(data[key]) == dict:
            new_data[key.split("_", 1)[0]] = key_beautify(data[key])
        if (type(data[key])) == list:
            new_data[key.split("_", 1)[0]] = []
            for item in data[key]:
                if type(item) == dict:
                    new_data[key.split("_", 1)[0]].append(key_beautify(item))
                else:
                    new_data[key.split("_", 1)[0]].append(item)
    return new_data


class SoftEtherAPI(object):
    admin_password = None
    socket = None
    connect_response = {}

    def __init__(self, hostname, port, password, verify=True, suffix="/api/"):
        self.socket = SoftEtherAPIConnector(hostname, port, password, suffix=suffix, verify=verify, hub=None)

    def call_method(self, function_name, payload=None):
        data = {
            "jsonrpc": "2.0",
            "id": "rpc_call_id",
            "method": function_name,
            "params": {
                'IntValue_int': [0],
            }
        }

        if payload is not None:
            data['params'] = serialize(payload)
        try:
            # print(json.dumps(data))
            result = self.socket.send_http_request(data)
            if "result" in result:
                result = key_beautify(result["result"])
                return result
            elif "error" in result:
                if result["error"]["code"] in ERRORS:
                    raise SoftEtherAPIException(ERRORS[result["error"]["code"]])
                else:
                    raise SoftEtherAPIException(result["error"]["message"])
        except Exception as e:
            return {"error": str(e)}

    def test(self):
        return self.call_method("Test")

    def get_server_info(self):
        return self.call_method('GetServerInfo')

    def get_server_status(self):
        return self.call_method('GetServerStatus')

    def create_listener(self, port=None, enable=None):
        payload = {
            'Port': ('int', [port]),
            'Enable': ('int', [enable])
        }

        return self.call_method('CreateListener', payload)

    def enum_listener(self):
        return self.call_method('EnumListener')

    def delete_listener(self, port=None):
        payload = {
            'Port': ('int', [port])
        }

        return self.call_method('DeleteListener', payload)

    def enable_listener(self, port=None, enable=None):
        payload = {
            'Port': ('int', [port]),
            'Enable': ('int', [enable])
        }

        return self.call_method('EnableListener', payload)

    def set_server_password(self, hashed_password=None):
        payload = {
            'HashedPassword': ('raw', [hashed_password])
        }

        return self.call_method('SetServerPassword', payload)

    def set_farm_setting(self, server_type=None, ports=None, public_ip=None, controller_name=None,
                         controller_port=None, member_password=None, weight=None, controller_only=None):
        payload = {
            'ServerType': ('int', [server_type]),
            'Ports': ('int', ports),
            'PublicIp': ('int', [public_ip]),
            'ControllerName': ('string', [controller_name]),
            'ControllerPort': ('int', [controller_port]),
            'MemberPassword': ('raw', [member_password]),
            'Weight': ('int', [weight]),
            'ControllerOnly': ('int', [controller_only])
        }

        return self.call_method('SetFarmSetting', payload)

    def get_farm_setting(self):
        return self.call_method('GetFarmSetting')

    def get_farm_info(self):
        return self.call_method('GetFarmInfo')

    def enum_farm_member(self):
        return self.call_method('EnumFarmMember')

    def get_farm_connection_status(self):
        return self.call_method('GetFarmConnectionStatus')

    def set_server_cert(self, cert=None, key=None, flag_1=None):
        payload = {
            'Cert': ('raw', [cert]),
            'Key': ('raw', [key]),
            'Flag1': ('int', [flag_1])
        }

        return self.call_method('SetServerCert', payload)

    def get_server_cert(self):
        return self.call_method('GetServerCert')

    def get_server_cipher(self, string=None):
        payload = {
            'String': ('string', [""])
        }

        return self.call_method('GetServerCipher', payload)

    def set_server_cipher(self, string=None):
        payload = {
            'String': ('string', [string])
        }

        return self.call_method('SetServerCipher', payload)

    def create_hub(self, hub_name=None, password=None, online=False, hub_type=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'AdminPasswordPlainText': ('string', [password]),
            'Online': ('int', [online]),
            'NoEnum': ('int', [True]),
            'HubType': ('int', [hub_type])
        }

        return self.call_method('CreateHub', payload)

    def set_hub(self, hub_name=None, password=None, online=None, hub_type=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'AdminPasswordPlainText': ('string', [password]),
            'Online': ('int', [online]),
            'HubType': ('int', [hub_type])
        }

        return self.call_method('SetHub', payload)

    def get_hub(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHub', payload)

    def enum_hub(self):
        return self.call_method('EnumHub')

    def delete_hub(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('DeleteHub', payload)

    def get_hub_radius(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHubRadius', payload)

    def set_hub_radius(self, hub_name=None, radius_server_name=None, radius_secret=None, radius_retry_interval=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'RadiusServerName': ('string', [radius_server_name]),
            'RadiusSecret': ('string', [radius_secret]),
            'RadiusRetryInterval': ('int', [radius_retry_interval])
        }

        return self.call_method('SetHubRadius', payload)

    def enum_connection(self):
        return self.call_method('EnumConnection')

    def disconnect_connection(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('DisconnectConnection', payload)

    def get_connection_info(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('GetConnectionInfo', payload)

    def set_hub_online(self, hub_name=None, online=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Online': ('int', [online])
        }

        return self.call_method('SetHubOnline', payload)

    def get_hub_status(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHubStatus', payload)

    def set_hub_log(self, hub_name=None, save_security_log=None, security_log_switch_type=None,
                    save_packet_log=None, packet_log_switch_type=None, packet_log_config=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'SaveSecurityLog': ('int', [save_security_log]),
            'SecurityLogSwitchType': ('int', [security_log_switch_type]),
            'SavePacketLog': ('int', [save_packet_log]),
            'PacketLogSwitchType': ('int', [packet_log_switch_type]),
            'PacketLogConfig': ('int', [packet_log_config])
        }

        return self.call_method('SetHubLog', payload)

    def get_hub_log(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHubLog', payload)

    def add_ca(self, hub_name=None, cert=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Cert': ('raw', [cert])
        }

        return self.call_method('AddCa', payload)

    def enum_ca(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumCa', payload)

    def get_ca(self, hub_name=None, key=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key])
        }

        return self.call_method('GetCa', payload)

    def delete_ca(self, hub_name=None, key=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key])
        }

        return self.call_method('DeleteCa', payload)

    def set_link_online(self, hub_name_ex=None, account_name=None):
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'AccountName': ('ustring', [account_name])
        }

        return self.call_method('SetLinkOnline', payload)

    def set_link_offline(self, hub_name_ex=None, account_name=None):
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'AccountName': ('ustring', [account_name])
        }

        return self.call_method('SetLinkOffline', payload)

    def delete_link(self, hub_name_ex=None, account_name=None):
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'AccountName': ('ustring', [account_name])
        }

        return self.call_method('DeleteLink', payload)

    def rename_link(self, hub_name_ex=None, old_account_name=None, new_account_name=None):
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'OldAccountName': ('ustring', [old_account_name]),
            'NewAccountName': ('ustring', [new_account_name])
        }

        return self.call_method('RenameLink', payload)

    def create_link(self, hub_name_ex=None, hub_name=None, online=None, hostname=None, port=None,account_name=None,
                    username=None,auth_type=None, password=None, no_udp_acceleration=None, use_encrypt=None,
                    use_compress=None,half_connection=None,disable_qos=None):   
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'HubName': ('string', [hub_name]),
            'AccountName': ('ustring', [account_name]),
            'Online': ('bool', [online]),
            'Hostname': ('string', [hostname]),
            'Port': ('int', [port]),
            'AuthType': ('int', [auth_type]),
            'Username': ('string', [username]),
            'NoUdpAcceleration': ('bool', [no_udp_acceleration]),
            'UseEncrypt': ('bool', [use_encrypt]),
            'UseCompress': ('bool', [use_compress])
        }
        if half_connection is not None:
            payload.update({'HalfConnection': ('bool', [half_connection])})
        
        if disable_qos is not None:
            payload.update({'DisableQoS': ('bool', [disable_qos])})
            
        if auth_type == 1:
            sha = sha0Hash()
            sha.update(password.encode('UTF-8') + username.upper().encode('UTF-8'))
            hash_password = sha.digest()
            hash_password = base64.b64encode(hash_password).decode('UTF-8')
            payload.update({'HashedPassword': ('raw', [hash_password])})
        elif auth_type == 2:
            payload.update({'PlainPassword': ('string', [password])})

        return self.call_method('CreateLink', payload)

    def get_link(self, hub_name_ex=None, account_name=""):
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'AccountName': ('ustring', [account_name])
        }

        return self.call_method('GetLink', payload)

    def set_link(self, hub_name_ex=None, online=None, auth_type=1, username=None,
                 expire_time=None,account_name=None,server_cert=None,check_server_cert=None,
                 password=None, no_udp_acceleration=None, use_encrypt=None, use_compress=False, policy=None):
        policy = policy or {}
        access = True
        sha = sha0Hash()
        sha.update(password.encode('UTF-8') + username.upper().encode('UTF-8'))
        hash_password = sha.digest()
        hashed_password = base64.b64encode(hash_password).decode('UTF-8')

        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'Online': ('int', [online]),
            "AccountName": ('ustring', [account_name]),
            'ExpireTime': ('datetime', [expire_time]),
            'AuthType': ('int', [auth_type]),
            'Username': ('string', [username]),
            'HashedPassword': ('raw', [hashed_password]),
            'NoUdpAcceleration': ('bool', [no_udp_acceleration]),
            'UseEncrypt': ('bool', [use_encrypt]),
            'UseCompress': ('bool', [use_compress]),

        }
        
        if check_server_cert:
            payload.update({'CheckServerCert': ('bool', [check_server_cert])})
            payload.update({'ServerCert': ('raw', [server_cert])})

        if policy is not None:
            access = policy.get('Access')
            max_download = policy.get('MaxDownload')
            max_upload = policy.get('MaxUpload')
            max_connection = policy.get('MaxConnection')
            vlan_id = policy.get('VlanId')
            payload.update({
                'Access': ('bool', [access]),
                'MaxDownload': ('int', [max_download * 1024 * 1024]),
                'MaxUpload': ('int', [max_upload * 1024 * 1024]),
                'MaxConnection': ('int', [max_connection]),
                'VlanId': ('int', [vlan_id])
            })

        return self.call_method('SetLink', payload)

    def enum_link(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumLink', payload)

    def get_link_status(self, hub_name_ex=None, account_name=None):
        payload = {
            'HubName_Ex': ('string', [hub_name_ex]),
            'AccountName': ('ustring', [account_name])
        }

        return self.call_method('GetLinkStatus', payload)

    def add_access(self, hub_name=None, id=None, note=None, active=None, priority=None, discard=None,
                   src_ip_address=None,
                   src_subnet_mask=None, dest_ip_address=None, dest_subnet_mask=None, protocol=None,
                   src_port_start=None, src_port_end=None, dest_port_start=None, dest_port_end=None,
                   src_username=None, dest_username=None, src_mac_address=None, src_mac_mask=None,
                   check_dst_mac=None, dst_mac_address=None, dst_mac_mask=None, check_tcp_state=None,
                   established=None, delay=None, jitter=None, loss=None, is_ipv6=None, unique_id=None,
                   redirect_url=None, src_ip_address_6=None, src_subnet_mask_6=None, dest_ip_address_6=None,
                   dest_subnet_mask_6=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Id': ('int', [id]),
            'Note': ('string', [note]),
            'Active': ('int', [active]),
            'Priority': ('int', [priority]),
            'Discard': ('int', [discard]),
            'SrcIpAddress': ('int', [src_ip_address]),
            'SrcSubnetMask': ('int', [src_subnet_mask]),
            'DestIpAddress': ('int', [dest_ip_address]),
            'DestSubnetMask': ('int', [dest_subnet_mask]),
            'Protocol': ('int', [protocol]),
            'SrcPortStart': ('int', [src_port_start]),
            'SrcPortEnd': ('int', [src_port_end]),
            'DestPortStart': ('int', [dest_port_start]),
            'DestPortEnd': ('int', [dest_port_end]),
            'SrcUsername': ('string', [src_username]),
            'DestUsername': ('string', [dest_username]),
            'SrcMacAddress': ('raw', [src_mac_address]),
            'SrcMacMask': ('raw', [src_mac_mask]),
            'CheckDstMac': ('int', [check_dst_mac]),
            'DstMacAddress': ('raw', [dst_mac_address]),
            'DstMacMask': ('raw', [dst_mac_mask]),
            'CheckTcpState': ('int', [check_tcp_state]),
            'Established': ('int', [established]),
            'Delay': ('int', [delay]),
            'Jitter': ('int', [jitter]),
            'Loss': ('int', [loss]),
            'IsIPv6': ('int', [is_ipv6]),
            'UniqueId': ('int', [unique_id]),
            'RedirectUrl': ('string', [redirect_url]),
            'SrcIpAddress6': ('raw', [src_ip_address_6]),
            'SrcSubnetMask6': ('raw', [src_subnet_mask_6]),
            'DestIpAddress6': ('raw', [dest_ip_address_6]),
            'DestSubnetMask6': ('raw', [dest_subnet_mask_6])
        }

        return self.call_method('AddAccess', payload)

    def delete_access(self, hub_name=None, id=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Id': ('int', [id])
        }

        return self.call_method('DeleteAccess', payload)

    def enum_access(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumAccess', payload)

    def set_access_list(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('SetAccessList', payload)

    def create_user(self, hub_name=None, name=None, auth_type=1, password=None,
                    note=None, created_time=None,
                    policy=None,radius_user=None,nt_user=None,
                    updated_time=None, expire_time=None, num_login=None):

        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name]),
            'Note': ('ustring', [note]),
            'CreatedTime': ('datetime', [created_time]),
            'UpdatedTime': ('datetime', [updated_time]),
            'ExpireTime': ('datetime', [expire_time]),
            'NumLogin': ('int', [num_login]),
            'AuthType': ('int', [auth_type]),
        }
        if policy is not None:
            access = policy.get('Access', True)
            max_download = policy.get('MaxDownload')
            max_upload = policy.get('MaxUpload')
            max_connection = policy.get('MaxConnection', 8)
            vlan_id = policy.get('VlanId')
            max_download = int(max_download) if max_download else 0
            max_upload = int(max_upload) if max_upload else 0
            payload.update({
                'policy:Access': ('bool', [access]),
                'policy:MaxDownload': ('int', [max_download * 1024 * 1024]),
                'policy:MaxUpload': ('int', [max_upload * 1024 * 1024]),
                'policy:MaxConnection': ('int', [max_connection]),
                'policy:VlanId': ('int', [vlan_id])
            })

        if auth_type == 1:
            payload.update({
                'Auth_Password': ('string', [password])
            })
        elif auth_type == 4:
            payload.update({
                'RadiusUsername': ('string', [radius_user])
            })
        elif auth_type == 5:
            payload.update({
                'NtUsername': ('string', [nt_user])
            })

        return self.call_method('CreateUser', payload)

    def set_user(self, hub_name=None, name=None, auth_type=None, password=None, user_cert=None, common_name=None,
                 radius_user=None, nt_user=None, group_name=None, realname=None, note=None, created_time=None,
                 updated_time=None, expire_time=None, num_login=None, policy=None):
        if password:
            hashed_key = sha0(password)
            hashed_key.update(str.encode(password))
            hashed_key.update(str.encode(str.upper(name)))
            hashed_key = hashed_key.digest()
            ntlm_secure_hash = sha0(password)
            ntlm_secure_hash.update(hashed_key)
            ntlm_secure_hash.update(self.connect_response['random'][0])
            ntlm_secure_hash = ntlm_secure_hash.digest()
        else:
            hashed_key = None
            ntlm_secure_hash = None
        if user_cert:
            user_cert = base64.b64decode(user_cert.encode())
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name]),
            'GroupName': ('string', [group_name]),
            'Realname': ('ustring', [realname]),
            'Note': ('ustring', [note]),
            'CreatedTime': ('int64', [created_time]),
            'UpdatedTime': ('int64', [updated_time]),
            'ExpireTime': ('int', [expire_time]),
            'NumLogin': ('int', [num_login]),
            'AuthType': ('int', [auth_type]),
            'HashedKey': ('raw', [hashed_key]),
            'NtLmSecureHash': ('raw', [ntlm_secure_hash]),
            'UserX': ('raw', [user_cert]),
            'CommonName': ('ustring', [common_name]),
            'RadiusUsername': ('string', [radius_user]),
            'NtUsername': ('string', [nt_user]),
            'UsePolicy': ('bool', [policy is not None]),
        }
        if policy is not None:
            access = policy.get('Access', True)
            max_download = policy.get('MaxDownload')
            max_upload = policy.get('MaxUpload')
            max_connection = policy.get('MaxConnection', 8)
            vlan_id = policy.get('VlanId')
            payload.update({
                'policy:Access': ('bool', [access]),
                'policy:MaxDownload': ('int', [max_download * 1024 * 1024]),
                'policy:MaxUpload': ('int', [max_upload * 1024 * 1024]),
                'policy:MaxConnection': ('int', [max_connection]),
                'policy:VlanId': ('int', [vlan_id])
            })

        return self.call_method('SetUser', payload)

    def get_user(self, hub_name=None, name=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name])
        }

        return self.call_method('GetUser', payload)

    def delete_user(self, hub_name=None, name=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name])
        }

        return self.call_method('DeleteUser', payload)

    def enum_user(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumUser', payload)

    def create_group(self, hub_name=None, name=None, realname=None, note=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name]),
            'Realname': ('ustring', [realname]),
            'Note': ('ustring', [note])
        }

        return self.call_method('CreateGroup', payload)

    def set_group(self, hub_name=None, name=None, realname=None, note=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name]),
            'Realname': ('ustring', [realname]),
            'Note': ('ustring', [note])
        }

        return self.call_method('SetGroup', payload)

    def get_group(self, hub_name=None, name=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name])
        }

        return self.call_method('GetGroup', payload)

    def delete_group(self, hub_name=None, name=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name])
        }

        return self.call_method('DeleteGroup', payload)

    def enum_group(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumGroup', payload)

    def enum_session(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumSession', payload)

    def get_session_status(self, hub_name=None, name=None, username=None, group_name=None, real_username=None,
                           session_status_client_ip=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name]),
            'Username': ('string', [username]),
            'GroupName': ('string', [group_name]),
            'RealUsername': ('string', [real_username]),
            'SessionStatus_ClientIp': ('int', [session_status_client_ip])
        }

        return self.call_method('GetSessionStatus', payload)

    def delete_session(self, hub_name=None, name=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name])
        }

        return self.call_method('DeleteSession', payload)

    def enum_mac_table(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumMacTable', payload)

    def delete_mac_table(self, hub_name=None, key=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key])
        }

        return self.call_method('DeleteMacTable', payload)

    def enum_ip_table(self, hub_name=None, key=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key])
        }

        return self.call_method('EnumIpTable', payload)

    def delete_ip_table(self):
        return self.call_method('DeleteIpTable')

    def set_keep(self, use_keep_connect=None, keep_connect_host=None, keep_connect_port=None,
                 keep_connect_protocol=None, keep_connect_interval=None):
        payload = {
            'UseKeepConnect': ('int', [use_keep_connect]),
            'KeepConnectHost': ('string', [keep_connect_host]),
            'KeepConnectPort': ('int', [keep_connect_port]),
            'KeepConnectProtocol': ('int', [keep_connect_protocol]),
            'KeepConnectInterval': ('int', [keep_connect_interval])
        }

        return self.call_method('SetKeep', payload)

    def get_keep(self):
        return self.call_method('GetKeep')

    def enable_secure_nat(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnableSecureNAT', payload)

    def disable_secure_nat(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('DisableSecureNAT', payload)

    # NOTE: mac_address, ip, mask, use_nat, use_dhcp, apply_dhcp_push_routes, save_log are
    def set_secure_nat_option(self, hub_name=None, use_nat=1, use_dhcp=1, save_log=1,
                              apply_dhcp_push_routes=1, mac_address=None, ip=None, mask=None,
                              mtu=0, nat_tcp_timeout=0, nat_udp_timeout=0,
                              dhcp_lease_ip_start=0, dhcp_lease_ip_end=0,
                              dhcp_subnet_mask=0, dhcp_expire_time_span=0,
                              dhcp_gateway_address=0, dhcp_dns_server_address=0,
                              dhcp_dns_server_address2=0, dhcp_domain_name="",
                              dhcp_push_routes=""):
        payload = {
            'RpcHubName': ('string', [hub_name]),
            'MacAddress': ('raw', [mac_address]),
            'Ip': ('int', [ip]),
            'Mask': ('int', [mask]),
            'UseNat': ('int', [use_nat]),
            'Mtu': ('int', [mtu]),
            'NatTcpTimeout': ('int', [nat_tcp_timeout]),
            'NatUdpTimeout': ('int', [nat_udp_timeout]),
            'UseDhcp': ('int', [use_dhcp]),
            'DhcpLeaseIPStart': ('int', [dhcp_lease_ip_start]),
            'DhcpLeaseIPEnd': ('int', [dhcp_lease_ip_end]),
            'DhcpSubnetMask': ('int', [dhcp_subnet_mask]),
            'DhcpExpireTimeSpan': ('int', [dhcp_expire_time_span]),
            'DhcpGatewayAddress': ('int', [dhcp_gateway_address]),
            'DhcpDnsServerAddress': ('int', [dhcp_dns_server_address]),
            'DhcpDnsServerAddress2': ('int', [dhcp_dns_server_address2]),
            'DhcpDomainName': ('string', [dhcp_domain_name]),
            'SaveLog': ('int', [save_log]),
            'ApplyDhcpPushRoutes': ('int', [apply_dhcp_push_routes]),
            'DhcpPushRoutes': ('string', [dhcp_push_routes])
        }

        return self.call_method('SetSecureNATOption', payload)

    def get_secure_nat_option(self, hub_name=None):
        payload = {
            'RpcHubName': ('string', [hub_name])
        }

        return self.call_method('GetSecureNATOption', payload)

    def enum_nat(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumNAT', payload)

    def enum_dhcp(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumDHCP', payload)

    def get_secure_nat_status(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetSecureNATStatus', payload)

    def enum_ethernet(self):
        return self.call_method('EnumEthernet')

    def add_local_bridge(self, device_name=None, hub_name_lb=None, tap_mode=None,
                         online=False, active=False):
        payload = {
            'DeviceName': ('string', [device_name]),
            'HubNameLB': ('string', [hub_name_lb]),
            'Online': ('bool', [online]),  # NOTE: always 0
            'Active': ('bool', [active]),  # NOTE: always 0
            'TapMode': ('int', [bool(tap_mode)])
        }

        return self.call_method('AddLocalBridge', payload)

    def delete_local_bridge(self, device_name=None, hub_name_lb=None, tap_mode=None):
        payload = {
            'DeviceName': ('string', [device_name]),
            'HubNameLB': ('string', [hub_name_lb]),
            'TapMode': ('int', [bool(tap_mode)])
        }

        return self.call_method('DeleteLocalBridge', payload)

    def enum_local_bridge(self):
        return self.call_method('EnumLocalBridge')

    def get_bridge_support(self):
        return self.call_method('GetBridgeSupport')

    def reboot_server(self):
        return self.call_method('RebootServer')

    def get_caps(self):
        return self.call_method('GetCaps')

    def get_config(self):
        return self.call_method('GetConfig')

    def set_config(self, file_name=None, file_data=None):
        payload = {
            'FileName': ('string', [file_name]),
            'FileData': ('raw', [file_data])
        }

        return self.call_method('SetConfig', payload)

    def get_default_hub_admin_options(self):
        return self.call_method('GetDefaultHubAdminOptions')

    def get_hub_admin_options(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHubAdminOptions', payload)

    def set_hub_admin_options(self, hub_name=None, name=None, value=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', name),
            'Value': ('int', value)
        }

        return self.call_method('SetHubAdminOptions', payload)

    def get_hub_ext_options(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHubExtOptions', payload)

    def set_hub_ext_options(self, hub_name=None, name=None, value=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', name),
            'Value': ('int', value)
        }

        return self.call_method('SetHubExtOptions', payload)

    def add_l3_switch(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('AddL3Switch', payload)

    def del_l3_switch(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('DelL3Switch', payload)

    def enum_l3_switch(self):
        return self.call_method('EnumL3Switch')

    def start_l3_switch(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('StartL3Switch', payload)

    def stop_l3_switch(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('StopL3Switch', payload)

    def add_l3_if(self, hub_name=None, name=None, ip_address=None, subnet_mask=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name]),
            'IpAddress': ('int', [ip_address]),
            'SubnetMask': ('int', [subnet_mask])
        }

        return self.call_method('AddL3If', payload)

    def del_l3_if(self, hub_name=None, name=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Name': ('string', [name])
        }

        return self.call_method('DelL3If', payload)

    def enum_l3_if(self):
        return self.call_method('EnumL3If')

    def add_l3_table(self, name=None, network_address=None, subnet_mask=None, gateway_address=None, metric=None):
        payload = {
            'Name': ('string', [name]),
            'NetworkAddress': ('int', [network_address]),
            'SubnetMask': ('int', [subnet_mask]),
            'GatewayAddress': ('int', [gateway_address]),
            'Metric': ('int', [metric])
        }

        return self.call_method('AddL3Table', payload)

    def del_l3_table(self, name=None):
        payload = {
            'Name': ('string', [name])
        }

        return self.call_method('DelL3Table', payload)

    def enum_l3_table(self):
        return self.call_method('EnumL3Table')

    def enum_crl(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('EnumCrl', payload)

    def add_crl(self, hub_name=None, key=None, serial=None, common_name=None,
                organization=None, unit=None, country=None, state=None,
                local=None, digest_md5=None, digest_sha1=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key]),
            'Serial': ('raw', [serial]),
            'CommonName': ('ustring', [common_name]),
            'Organization': ('ustring', [organization]),
            'Unit': ('ustring', [unit]),
            'Country': ('ustring', [country]),
            'State': ('ustring', [state]),
            'Local': ('ustring', [local]),
            'DigestMD5': ('raw', [digest_md5]),
            'DigestSHA1': ('raw', [digest_sha1])
        }

        return self.call_method('AddCrl', payload)

    def del_crl(self, hub_name=None, key=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key])
        }

        return self.call_method('DelCrl', payload)

    def get_crl(self, hub_name=None, key=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key])
        }

        return self.call_method('GetCrl', payload)

    def set_crl(self, hub_name=None, key=None, serial=None, common_name=None,
                organization=None, unit=None, country=None, state=None, local=None,
                digest_md5=None, digest_sha1=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Key': ('int', [key]),
            'Serial': ('raw', [serial]),
            'CommonName': ('ustring', [common_name]),
            'Organization': ('ustring', [organization]),
            'Unit': ('ustring', [unit]),
            'Country': ('ustring', [country]),
            'State': ('ustring', [state]),
            'Local': ('ustring', [local]),
            'DigestMD5': ('raw', [digest_md5]),
            'DigestSHA1': ('raw', [digest_sha1])
        }

        return self.call_method('SetCrl', payload)

    def set_ac_list(self, hub_name=None, num_item=None, deny=None, ip_address=None,
                    masked=None, subnet_mask=None, priority=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'NumItem': ('int', [num_item]),
            'Deny': ('int', deny),
            'IpAddress': ('int', ip_address),
            'Masked': ('int', masked),
            'SubnetMask': ('int', subnet_mask),
            'Priority': ('int', priority)
        }

        return self.call_method('SetAcList', payload)

    def get_ac_list(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetAcList', payload)

    def enum_log_file(self):
        return self.call_method('EnumLogFile')

    def read_log_file(self, file_path=None, server_name=None, offset=None):
        payload = {
            'FilePath': ('string', [file_path]),
            'ServerName': ('string', [server_name]),
            'Offset': ('int', [offset])
        }

        return self.call_method('ReadLogFile', payload)

    def add_license_key(self):
        return self.call_method('AddLicenseKey')

    def del_license_key(self):
        return self.call_method('DelLicenseKey')

    def enum_license_key(self):
        return self.call_method('EnumLicenseKey')

    def get_license_status(self):
        return self.call_method('GetLicenseStatus')

    def set_sys_log(self):
        return self.call_method('SetSysLog')

    def get_sys_log(self):
        return self.call_method('GetSysLog')

    def enum_eth_v_lan(self):
        return self.call_method('EnumEthVLan')

    def set_enable_eth_v_lan(self):
        return self.call_method('SetEnableEthVLan')

    def set_hub_msg(self, hub_name=None, msg=None):
        payload = {
            'HubName': ('string', [hub_name]),
            'Msg': ('raw', [msg])
        }

        return self.call_method('SetHubMsg', payload)

    def get_hub_msg(self, hub_name=None):
        payload = {
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetHubMsg', payload)

    def crash(self):
        return self.call_method('Crash')

    def get_admin_msg(self):
        return self.call_method('GetAdminMsg')

    def flush(self):
        return self.call_method('Flush')

    def debug(self):
        return self.call_method('Debug')

    def set_ipsec_services(self, l2tp_raw=None, l2tp_ipsec=None, ipsec_secret=None, l2tp_default_hub=None):
        payload = {
            'L2TP_Raw': ('int', [l2tp_raw]),
            'L2TP_IPsec': ('int', [l2tp_ipsec]),
            'IPsec_Secret': ('string', [ipsec_secret]),
            'L2TP_DefaultHub': ('string', [l2tp_default_hub])
        }

        return self.call_method('SetIPsecServices', payload)

    def get_ipsec_services(self):
        return self.call_method('GetIPsecServices')

    def add_ether_ip_id(self, id=None, hub_name=None, user_name=None, password=None):
        payload = {
            'Id': ('string', [id]),
            'HubName': ('string', [hub_name]),
            'UserName': ('string', [user_name]),
            'Password': ('string', [password])
        }

        return self.call_method('AddEtherIpId', payload)

    def get_ether_ip_id(self, id=None, hub_name=None):
        payload = {
            'Id': ('string', [id]),
            'HubName': ('string', [hub_name])
        }

        return self.call_method('GetEtherIpId', payload)

    def delete_ether_ip_id(self, id=None, hub_name=None):
        payload = {
            'Id': ('string', [id]),
            'HubName': ('string', [hub_name])
        }

        return self.call_method('DeleteEtherIpId', payload)

    def enum_ether_ip_id(self):
        return self.call_method('EnumEtherIpId')

    def set_open_vpn_sstp_config(self, enable_open_vpn=None, enable_sstp=None, open_vpn_port_list=None):
        payload = {
            'EnableOpenVPN': ('int', [enable_open_vpn]),
            'EnableSSTP': ('int', [enable_sstp]),
            'OpenVPNPortList': ('string', [open_vpn_port_list])
        }

        return self.call_method('SetOpenVpnSstpConfig', payload)

    def get_open_vpn_sstp_config(self):
        return self.call_method('GetOpenVpnSstpConfig')

    def get_ddns_client_status(self):
        return self.call_method('GetDDnsClientStatus')

    def change_ddns_client_hostname(self):
        return self.call_method('ChangeDDnsClientHostname')

    def regenerate_server_cert(self):
        return self.call_method('RegenerateServerCert')

    def make_open_vpn_config_file(self):
        return self.call_method('MakeOpenVpnConfigFile')

    def set_special_listener(self, vpn_over_icmp_listener=None, vpn_over_dns_listener=None):
        payload = {
            'VpnOverIcmpListener': ('int', [vpn_over_icmp_listener]),
            'VpnOverDnsListener': ('int', [vpn_over_dns_listener])
        }

        return self.call_method('SetSpecialListener', payload)

    def get_special_listener(self):
        return self.call_method('GetSpecialListener')

    def get_azure_status(self):
        return self.call_method('GetAzureStatus')

    def set_azure_status(self, is_connected=None, is_enabled=None):
        payload = {
            'IsConnected': ('int', [is_connected]),
            'IsEnabled': ('int', [is_enabled])
        }

        return self.call_method('SetAzureStatus', payload)

    def get_ddns_internet_settng(self):
        return self.call_method('GetDDnsInternetSettng')

    def set_ddns_internet_settng(self, proxy_type=None, proxy_host_name=None, proxy_port=None,
                                 proxy_username=None, proxy_password=None):
        payload = {
            'ProxyType': ('int', [proxy_type]),
            'ProxyHostName': ('string', [proxy_host_name]),
            'ProxyPort': ('int', [proxy_port]),
            'ProxyUsername': ('string', [proxy_username]),
            'ProxyPassword': ('string', [proxy_password])
        }

        return self.call_method('SetDDnsInternetSettng', payload)
