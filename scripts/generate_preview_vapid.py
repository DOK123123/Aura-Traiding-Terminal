"""OWNER-RUN ONLY. Write a new Preview-only VAPID pair to an exclusive 0600 file.
Never prints key material, uploads it or changes any deployment/environment.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--subject',required=True)
    args=parser.parse_args()
    target=args.output.resolve()
    if target.is_relative_to(Path(__file__).resolve().parents[1]):
        parser.error('Output must be outside the repository')
    if not re.fullmatch(r'mailto:[^\s@]+@[^\s@]+\.[^\s@]+',args.subject):
        parser.error('Subject must be an owner-controlled mailto contact')
    key=ec.generate_private_key(ec.SECP256R1())
    encode=lambda b:base64.urlsafe_b64encode(b).decode().rstrip('=')
    values={'AURA_PREVIEW_VAPID_PRIVATE_KEY':encode(key.private_numbers().private_value.to_bytes(32,'big')),
            'AURA_PREVIEW_VAPID_PUBLIC_KEY':encode(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)),
            'AURA_PREVIEW_VAPID_SUBJECT':args.subject}
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as out:json.dump(values,out,indent=2);out.write('\n')
    print('VAPID pair written to the selected private file. Key values were not printed.')

if __name__=='__main__':main()
