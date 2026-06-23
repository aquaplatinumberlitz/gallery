#!/bin/bash
# Sửa rebase todo: đổi pick thành fixup cho 3 scratch commits
sed -i '/5b00831/s/^pick/fixup/; /3f48b5c/s/^pick/fixup/; /abaacab/s/^pick/fixup/' "$1"
