"""Laposte XML -> Python."""

import base64
from datetime import datetime
from lxml import objectify
from pprint import pprint

from roulier.codec import DecoderGetLabel

from .constants import SERVICE_PandR
from .constants import SERVICE_PandS


class GlsEuDecoderGetLabel(DecoderGetLabel):
    def decode(self, response, input_payload):
        pprint(response)
        """
        Decodes JSON returned by GLS and formats it to roulier standardization
        """
        body = response["body"]
        parcels = []
        annexes = []
        cc = 0
        for gls_parcel in body["CreatedShipment"]["ParcelData"]:
            parcel = {
                "id": gls_parcel["ParcelNumber"],
                "reference": gls_parcel["ParcelNumber"],
                "tracking": {
                    "number": gls_parcel["TrackID"],
                    "url": gls_parcel["TrackID"],
                    "partner": "",
                },
                "label": {
                    "data": body["CreatedShipment"]["PrintData"][cc]["Data"],
                    "name": "label_1",
                    "type": body["CreatedShipment"]["PrintData"][cc]["LabelFormat"],
                }
            }
            cc += 1
            parcels.append(parcel)
        self.result["parcels"] += parcels
        self.result["annexes"] += annexes
