""" Taken from Cisco's axl_addGateway example script and modified to do a swap of VG types, like for like on port count

for example, swap a vg204 to a vg400, vg310 to vg410-24, etc.

Cisco's work can be found here: https://github.com/CiscoDevNet/axl-python-zeep-samples/

Copyright (c) 2023 Cisco and/or its affiliates.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the 'Software'), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from lxml import etree
from requests import Session
from requests.auth import HTTPBasicAuth

from zeep import Client, Settings, Plugin, xsd
from zeep.transports import Transport
from zeep.exceptions import Fault
import sys
import urllib3

# Edit .env file to specify your Webex site/user details
import os
from dotenv import load_dotenv

# the .env file should have the following 3 variables:
# CUCM_HOSTNAME=
# CUCM_USERNAME=
# CUCM_PASSWORD=""

load_dotenv()

# Change to true to enable output of request/response headers and XML
# Verbose will print header output for every response, quite chatty!  It also relies on DEBUG to be enabled

DEBUG = False
VERBOSE = False

# The WSDL is a local file in the working directory, change this to the current location as needed
WSDL_FILE = "schema/current/AXLAPI.wsdl"

# This class lets you view the incoming and outgoing http headers and XML
class MyLoggingPlugin(Plugin):
    def egress(self, envelope, http_headers, operation, binding_options):
        # Format the request body as pretty printed XML
        xml = etree.tostring(envelope, pretty_print=True, encoding="unicode")

        if VERBOSE:
            print(f"\nDEBUG -- HEADERS\n\nRequest\n-------\nHeaders:\n{ http_headers }\n\nBody:\n{ xml }")

    def ingress(self, envelope, http_headers, operation):
        # Format the response body as pretty printed XML
        xml = etree.tostring(envelope, pretty_print=True, encoding="unicode")

        if VERBOSE:
            print(f"\nResponse\n-------\nHeaders:\n{ http_headers }\n\nBody:\n{ xml }")

# Session setup
# The first step is to create a SOAP client session
session = Session()

# We avoid certificate verification by default
# And disable insecure request warnings to keep the output clear
session.verify = False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# To enable SSL cert checking (recommended for production)
# place the CUCM Tomcat cert .pem file in the root of the project
# and uncomment the two lines below

# CERT = 'changeme.pem'
# session.verify = CERT

session.auth = HTTPBasicAuth(os.getenv("CUCM_USERNAME"), os.getenv("CUCM_PASSWORD"))

transport = Transport(session=session, timeout=10)

# strict=False is not always necessary, but it allows Zeep to parse imperfect XML
settings = Settings(strict=False, xml_huge_tree=True)

# If debug output is requested, add the MyLoggingPlugin callback
plugin = [MyLoggingPlugin()] if DEBUG else []

# Create the Zeep client with the specified settings
client = Client(WSDL_FILE, settings=settings, transport=transport, plugins=plugin)

# Create the Zeep service binding to AXL at the specified CUCM
service = client.create_service(
    "{http://www.cisco.com/AXLAPIService/}AXLAPIBinding",
    f'https://{os.getenv( "CUCM_HOSTNAME" )}:8443/axl/',
)

######################
### Main app start
######################

print("Gateway Swap")
print('\n\nPlease enter the hostname for the VG\n')

#### Temp for testing
domain = input('VG with domain / FQDN: ')

# Get the gateway details
try:
    resp = service.getGateway(domainName=domain)

except Fault as err:
    print(f"Check your gateway name in CUCM.\n\nZeep error: getGateway: { err }")
    sys.exit(1)

gateway = resp["return"]["gateway"]
gatewaytype = resp["return"]["gateway"]["product"]
callManagerGroupName = resp["return"]["gateway"]["callManagerGroupName"]["_value_1"]
gatewaydesc = resp["return"]["gateway"]["description"]

if DEBUG:
    print("\nGATEWAY details\n\n")
    print("type: ", gatewaytype)
    print("CUCM group: ",callManagerGroupName)
    print("VG Desc: ", gatewaydesc)
    print("\ngetGateway: Success\n")
    print(f"\n==> Gateway uuid: { gateway['uuid'] }\n")
    print("\n\nFull response:", resp)
 
# There is currently not a good way to retrieve the endpoints associated
# a MGCP gateway using regular AXL requests - <executeSQLQuery> will be used.

# Raw UUID values in the CUCM database are stored without braces ("{}")
# and in lower case - regular AXL requests normalize these by uppercasing
# and surrouding with braces.  This must be undone to use the uuid in
# an <executeSQLQuery> request.
raw_uuid = gateway["uuid"].lower()[1:-1]
sql = f"SELECT * FROM mgcpdevicemember WHERE fkmgcp='{raw_uuid}'"
try:
    resp = service.executeSQLQuery(sql=sql)

except Fault as err:
    print(f"Zeep error: executeSQLQuery: { err }")
    sys.exit(1)

ports = resp["return"]["row"]

if DEBUG:
    print("\nPORT info debug\n\nexecuteSQLQuery: Success")
    print(f"Domain: { gateway['domainName']}\n")
    print(f"\n==> Port count: { len(ports) }\n")
    input("Press Enter to continue... :")

#####

# # Create an gateway object specifying VG310 MGCP gateway with
# #   VG-2VWIC-MBRD unit and 24FXS subunit
# setting name of vg with new- in the name, we aren't removing the old gateway, just creating a new one with the new vg type
domain = "new-" + domain

# VG Swap rules
# VG204 -> vg400 (4fxs/4fxo)
# vg310 -> vg410 (24fxs)
# vg320 -> vg410 (48fxs)
#
# don't try to use the vg420, it's got an 84 or 144 port card, not the same as the 320, use the 410-48 config for the 320 replacement

if gatewaytype == "VG204":
    # settings for vg400 4FXS/4FXO follow
    unit = 0
    subunit = 1
    gateway = {
        "domainName": domain,
        "product": "VG400",
        "protocol": "MGCP",
        "description": gatewaydesc,
        "callManagerGroupName": callManagerGroupName,
            "units": {
                "unit": [
                    {
                        "index": unit,
                        "product": "VG-1NIM-MBRD",
                        "subunits": {
                            "subunit": [{"index": subunit, "product": "VG-4FXS/4FXO", "beginPort": 0}]
                        },
                    }
                ]
            },
        }

if gatewaytype == "VG310":
    # settings for vg410-24 follow
    unit = 0
    subunit = 1
    gateway = {
        "domainName": domain,
        "product": "VG410",
        "protocol": "MGCP",
        "description": gatewaydesc,
        "callManagerGroupName": callManagerGroupName,
            "units": {
                "unit": [
                    {
                        "index": unit,
                        "product": "VG-1NIM-MBRD",
                        "subunits": {
                            "subunit": [{"index": subunit, "product": "VG-24FXS", "beginPort": 0}]
                        },
                    }
                ]
            },
        }

if gatewaytype == "VG320":
    # settings for vg410-48 follow
    unit = 0
    subunit = 1
    gateway = {
        "domainName": domain,
        "product": "VG410",
        "protocol": "MGCP",
        "description": gatewaydesc,
        "callManagerGroupName": callManagerGroupName,
            "units": {
                "unit": [
                    {
                        "index": unit,
                        "product": "VG-1NIM-MBRD",
                        "subunits": {
                            "subunit": [{"index": subunit, "product": "VG-48FXS", "beginPort": 0}]
                        },
                    }
                ]
            },
        }

# To add vendorConfig items, create lxml Element objects and append to
# an array named vendorConfig, a child element under <units>
ModemPassthrough = etree.Element("ModemPassthrough")
ModemPassthrough.text = "Disable"
T38FaxRelay = etree.Element("T38FaxRelay")
T38FaxRelay.text = "Enable"
#DtmfRelay = etree.Element("DtmfRelay")
#DtmfRelay.text = "NTE-CA"

# Append each top-level element to an array
vendorConfig = []
vendorConfig.append(ModemPassthrough)
vendorConfig.append(T38FaxRelay)
#vendorConfig.append(DtmfRelay)

# Create a Zeep xsd type object of type XVendorConfig from the client object
xvcType = client.get_type("ns0:XVendorConfig")

# Use the XVendorConfig type object to create a vendorConfig object
#   using the array of vendorConfig elements from above, and set as
#   phone.vendorConfig

gateway["vendorConfig"] = xvcType(vendorConfig)

# Execute the addGateway request
try:
    resp = service.addGateway(gateway)

except Fault as err:
    print(f"Zeep error: addGateway: { err }")
    sys.exit(1)

print("\nGateway Added Successfully\n")
if DEBUG:
    print("\naddGateway response:\n")
    print(resp, "\n")
    input("Press Enter to continue...")

# Get details for each port

# <executeSQLQuery> return is an "xsd:any" type, which Zeep models
# as a array of rows, with database column name as the tag property.
# We'll create a function to access this data in a more intuitive way
def get_column(tag, row):
    element = list(filter(lambda x: x.tag == tag, row))
    return element[0].text if len(element) > 0 else None

# cycle through the ports
for port in ports:
    try:
        resp = service.getGatewayEndpointAnalogAccess(uuid=get_column("fkdevice", port))
    except Fault as err:
        print(f"Zeep error: getGatewayEndpointAnalogAccess: { err }")
        sys.exit(1)
    
    slotnum = resp["return"]["gatewayEndpointAnalogAccess"]["subunit"]
    if slotnum == 1:
        portnum = int(resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["index"]) + 24
    else:
        portnum = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["index"]

    name = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["name"]
    devicePoolName = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["devicePoolName"]["_value_1"]
    locationName = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["locationName"]["_value_1"]
    dn = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["port"]["lines"]["line"]["dirn"]["pattern"]
    pt = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["port"]["lines"]["line"]["dirn"]["routePartitionName"]["_value_1"]
    dn_display = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["port"]["lines"]["line"]["display"]
    dn_extmask = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["port"]["lines"]["line"]["e164Mask"]
    portdesc = resp["return"]["gatewayEndpointAnalogAccess"]["endpoint"]["description"]

    if DEBUG:
        print(resp)
        print("\n\n Specific details on the port:")
        print("slotnum :", slotnum)
        print("portnum :", portnum)
        print("name: ", name)
        print("dn :", dn)
        print("callerID :", dn_display)
        print("external mask :", dn_extmask)
        print("device pool :", devicePoolName)
        print("location :", locationName)
        print("partition :", pt)

    # Create a gateway analog access endpoint object
    # This should be close to the minimum possible fields
    portName = f"AALN/S{ unit }/SU{ subunit }/{ portnum }@{ domain }"
    endpoint = {
        "domainName": domain,
        "unit": unit,
        "subunit": subunit,
        "endpoint": {
            "index": portnum,
            "name": portName,
            "description": portdesc,
            "product": "Cisco MGCP FXS Port",
            "class": "Gateway",
            "protocol": "Analog Access",
            "protocolSide": "User",
            "devicePoolName": devicePoolName,
            "locationName": locationName,
            "port": {
                "portNumber": 1,
                "callerIdEnable": False,
                "callingPartySelection": "Originator",
                "expectedDigits": 10,
                "sigDigits": {"_value_1": 10, "enable": False},
                "lines": {
                    "line": [
                        {
                            "index": 1,
                            "dirn": {"pattern": dn, "routePartitionName": pt},
                            "display": dn_display,
                            "e164Mask": dn_extmask,
                        }
                    ]
                },
                "presentationBit": "Allowed",
                "silenceSuppressionThreshold": "Disable",
                "smdiPortNumber": 2048,
                "trunk": "POTS",
                "trunkDirection": "Bothways",
                "trunkLevel": "ONS",
                "trunkPadRx": "NoDbPadding",
                "trunkPadTx": "NoDbPadding",
                "timer1": 200,
                "timer2": 0,
                "timer3": 100,
                "timer4": 1000,
                "timer5": 0,
                "timer6": 0,
            },
            "trunkSelectionOrder": "Top Down",
        },
    }

    # Execute the addGatewayEndpointAnalogAccess request
    try:
        resp = service.addGatewayEndpointAnalogAccess(endpoint)

    except Fault as err:
        print(f"Zeep error: addGatewayEndpointAnalogAccess: { err }")
        sys.exit(1)

    if DEBUG:
        print("\n\n=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-\naddGatewayEndpointAnalogAccess response:\n")
        print(resp, "\n")
