"""Transform input to laposte compatible xml."""

from jinja2 import Environment, PackageLoader
import logging

from roulier.codec import Encoder
from roulier.exception import InvalidApiInput

from .constants import SERVICE_FDS
from .constants import SERVICE_SHD
from .constants import SERVICE_SRS

_logger = logging.getLogger(__name__)


class GlsEuEncoderBase(Encoder):
    def transform_input_to_carrier_webservice(self, data):
        """
        Transforms standard roulier input into gls specific request data
        """
        body = {
            "Shipment": {
                "Product": data['service']['product'],
                "ShippingDate": "%s" % data["service"]["shippingDate"],
                "ShipmentUnit": [{
                    "Weight": data['parcels'][0]['weight'],
                }]
            },
            "PrintingOptions": {
                "ReturnLabels": {
                    "TemplateSet": "NONE",
                    "LabelFormat": data["service"]["labelFormat"]
                },
            },
        }
        if data['service']['service'] == 'service_shopdelivery':
            body["Shipment"]["Service"] = [{
                "ShopDelivery": {
                    "ServiceName": data['service']['service'],
                    "ParcelShopID": data['service']['shop_id'],
                }
            }]
        elif data['service']['service'] == 'service_shopreturn':
            body["Shipment"]["Service"] = [{
                "ShopReturn": {
                    "ServiceName": data['service']['service'],
                    "NumberOfLabels": data['service']['number_of_parcel'],
                }
            }]
        elif data['service']['service'] in ('service_pickandship','service_pickandreturn'):
            body["Shipment"]["Service"] = [{
                "PickAndShip": {
                    "ServiceName": data['service']['service'],
                    "PickupDate": data['service']['pickup_date'],
                }
            }]
        else:
            if data['service']['service'] :
                body["Shipment"]["Service"] = [{
                    "Service": {
                        "ServiceName": data['service']['service'] or "",
                    }
                }]

        if data["service"].get("incoterm"):
            body["Shipment"]["IncotermCode"] = data["service"]["incoterm"]
        body["Shipment"].update(self._transforms_addresses(data, body))
        body["Shipment"]["Shipper"]["ContactID"] = data["service"]["customerId"]
        # if "return" in body["addresses"] and data.get("return_weight"):
        #     body["returns"] = {"weight": "%.2f" % data["return_weight"]}
        references = [
            ref.strip()
            for ref in (
                data["service"].get("reference1", ""),
                data["service"].get("reference2", ""),
                data["service"].get("reference3", ""),
            )
            if ref.strip()
        ]
        if references:
            body["Shipment"]["ShipmentReference"] = references
        # if data.get("returns") and "return" in body["addresses"]:
        #     body["returns"] = [
        #         {"weight": "%.2f" % ret["weight"]}
        #         for ret in data.get("returns")
        #         if ret.get("weight")
        #     ]
        # body["parcels"] = self._transforms_parcels(data, body)
        return {
            "body": body,
            "auth": data["auth"],
            "language": data["service"].get("language", "en"),
        }

    def _transforms_addresses(self, data, body):
        """
        Transforms standard roulier addresses input into gls specific request data
        """
        addresses = {}
        available_addr = (("to_address", "Consignee", "Address"),)
        if data.get("from_address"):
            available_addr += (("from_address", "Shipper", "AlternativeShipperAddress"),)
        if data.get("return_address"):
            available_addr += (("return_address", "return", "Address"),)
        if data.get("pickup_address"):
            available_addr += (("pickup_address", "pickup", "Address"),)

        addr_req_fields = (
            ("name", "Name1"),  # Raison sociale ou nom destinataire
            (
                "street1",
                "Street",
            ),  # Adresse principale => si adresse sur plusieurs lignes, renseigner le nom de la rue ICI
            (
                "country",
                "CountryCode",
            ),  # deux lettres du code pays -> ISO 3166-1-alpha-2 (ex: "FR")
            (
                "zip",
                "ZIPCode",
            ),  # code postal (cas particulier: province pour l'Irlande)
            ("city", "City"),  # Ville
        )
        addr_opt_fields = (
            (
                "id",
                "id",
            ),  # Identifiant adresse (référence utilisable pour recherche track&trace sur notre site YourGLS)
            ("street2", "Name2"),  # Complément d'adresse
            ("street3", "Name3"),  # Complément d'adresse
            (
                "blockNo1",
                "blockNo1",
            ),  # Numéro de la maison ou de l'immeuble dans la rue - apparait à la suite du champ "Street1" sur l'étiquette - Ne renseigner QUE si non présent dans les informations mises en "Street1"
            ("contact", "ContactPerson"),  # Nom d'un contact
            ("phone", "FixedLinePhonenumber"),  # Numéro de téléphone : obligatoire si pas de mobile
            (
                "mobile",
                "MobilePhoneNumber",
            ),  # Numéro de téléphone mobile : obligatoire si pas de fixe
            ("email", "eMail"),  # Adresse E-mail - /!\Obligatoire en BtoC
        )
        for from_addr, to_addr, field_addr in available_addr:
            addr = data.get(from_addr)
            if not addr:
                continue
            # if the company address field is set, then the name is actually the contact
            if addr["company"] and addr["name"]:
                addr["contact"] = addr["name"]
                addr["name"] = addr["company"]
            addresses[to_addr] = dict()
            addresses[to_addr][field_addr] = dict(
                (to_field, addr[from_field]) for from_field, to_field in addr_req_fields
            )
            addresses[to_addr][field_addr]["CountryCode"] = addresses[to_addr][field_addr]["CountryCode"].upper()
            addresses[to_addr][field_addr].update(
                dict(
                    (to_field, addr[from_field])
                    for from_field, to_field in addr_opt_fields
                    if addr.get(from_field)
                )
            )
            if addresses[to_addr][field_addr]["CountryCode"] == "IR" and addr.get("province"):
                addresses[to_addr][field_addr]["province"] = addr.get("province")
        return addresses

    def _transforms_parcels(self, data, body):
        """
        Transforms standard roulier parcels input into gls specific request data
        """
        parcels = []
        global_sevice = (
            self._set_service(data["service"], body)
            if "product" in data["service"]
            else None
        )
        for p in data["parcels"]:
            parcel = {"weight": "%.2f" % p["weight"]}
            refs = []
            if p.get("reference"):
                refs.append(p["reference"])
            if p.get("reference2"):
                refs.append(p["reference2"])
            if refs:
                parcel["references"] = refs
            if p.get("comment"):
                parcel["comment"] = p["comment"]
            if "services" in p:
                services = []
                for subdata in p["services"]:
                    service = self._set_service(subdata, body)
                    if service:
                        services.append(service)
                if global_sevice:
                    services.append(global_sevice)
                if services:
                    parcel["services"] = services
            parcels.append(parcel)
        return parcels

    def _set_service(self, subdata, body):
        service_name = subdata.get("product")
        if service_name not in (SERVICE_FDS, SERVICE_SHD, SERVICE_SRS):
            return  # service must only be included fot those three ones
        service = {"name": service_name}
        if service_name == SERVICE_SHD:
            pickup_id = subdata.get("pickupLocationId")
            service["infos"] = [
                {
                    "name": "parcelshopid" if pickup_id else "directshop",
                    "value": pickup_id or "Y",
                }
            ]
        elif service_name == SERVICE_SRS and "pickup" in body["addresses"]:
            service["infos"] = [{"name": "returnonly", "value": "Y"}]
        return service


class GlsEuEncoder(GlsEuEncoderBase):
    """Transform input to laposte compatible xml."""

    pass
