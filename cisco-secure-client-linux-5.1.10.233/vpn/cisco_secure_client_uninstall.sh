#!/bin/sh

INSTPREFIX="/opt/cisco/secureclient"
BINDIR="${INSTPREFIX}/bin"
NVM_BINDIR="${INSTPREFIX}/NVM/bin"
POSTURE_BINDIR="${INSTPREFIX}/securefirewallposture/bin"

VPN_UNINST=${BINDIR}/vpn_uninstall.sh
POSTURE_UNINST=${POSTURE_BINDIR}/posture_uninstall.sh
NVM_UNINST=${NVM_BINDIR}/nvm_uninstall.sh
ISEPOSTURE_UNINST=${BINDIR}/iseposture_uninstall.sh
ISECOMPLIANCE_UNINST=${BINDIR}/isecompliance_uninstall.sh

if [ -x "${ISECOMPLIANCE_UNINST}" ]; then
  ${ISECOMPLIANCE_UNINST}
  if [ $? -ne 0 ]; then
    echo "Error uninstalling Cisco Secure Client - ISE Compliance."
  fi
fi

if [ -x "${ISEPOSTURE_UNINST}" ]; then
  ${ISEPOSTURE_UNINST}
  if [ $? -ne 0 ]; then
    echo "Error uninstalling Cisco Secure Client - ISE Posture."
  fi
fi

if [ -x "${POSTURE_UNINST}" ]; then
  ${POSTURE_UNINST}
  if [ $? -ne 0 ]; then
    echo "Error uninstalling Cisco Secure Client - Secure Firewall Posture Module."
  fi
fi

if [ -x "${NVM_UNINST}" ]; then
  ${NVM_UNINST}
  if [ $? -ne 0 ]; then
  echo "Error uninstalling Cisco Secure Client - Network Visibility Module."
  fi
fi


if [ -x "${VPN_UNINST}" ]; then
  ${VPN_UNINST}
  if [ $? -ne 0 ]; then
    echo "Error uninstalling Cisco Secure Client."
  fi
fi

exit 0
