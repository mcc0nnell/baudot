#!/usr/bin/env python3
import argparse
from pathlib import Path


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--ami-port", type=int, required=True)
    p.add_argument("--sip-port", type=int, required=True)
    p.add_argument("--peer-port", type=int, required=True)
    p.add_argument("--agent-extension", required=True)
    p.add_argument("--provider-id", required=True)
    p.add_argument("--from-tn", required=True)
    p.add_argument("--cte-base", required=True)
    p.add_argument("--agi-script", required=True)
    p.add_argument("--agi-trace", required=True)
    p.add_argument("--module-dir", required=True)
    p.add_argument("--rtp-start", type=int, required=True)
    p.add_argument("--rtp-end", type=int, required=True)
    args = p.parse_args()

    root = Path(args.root).resolve()
    etc = root / "etc"
    for sub in [
        root / "var/lib/asterisk/keys",
        root / "var/lib/asterisk/agi-bin",
        root / "var/spool/asterisk",
        root / "var/run/asterisk",
        root / "var/log/asterisk",
    ]:
        sub.mkdir(parents=True, exist_ok=True)

    write(etc / "asterisk.conf", f"""[directories]
astetcdir => {etc}
astmoddir => {Path(args.module_dir).resolve()}
astvarlibdir => {root / 'var/lib/asterisk'}
astdbdir => {root / 'var/lib/asterisk'}
astkeydir => {root / 'var/lib/asterisk/keys'}
astdatadir => {root / 'var/lib/asterisk'}
astagidir => {root / 'var/lib/asterisk/agi-bin'}
astspooldir => {root / 'var/spool/asterisk'}
astrundir => {root / 'var/run/asterisk'}
astlogdir => {root / 'var/log/asterisk'}
astsbindir => /usr/sbin

[options]
verbose = 3
debug = 0
nofork = yes
quiet = no
timestamp = yes
""")

    write(etc / "modules.conf", """[modules]
autoload=yes
""")
    write(etc / "logger.conf", """[general]
dateformat=%F %T

[logfiles]
console => notice,warning,error,verbose
messages => notice,warning,error,verbose
""")
    write(etc / "manager.conf", f"""[general]
enabled = yes
webenabled = no
port = {args.ami_port}
bindaddr = 127.0.0.1
displayconnects = no

[baudot]
secret = synthetic
read = all
write = all
""")
    write(etc / "rtp.conf", f"""[general]
rtpstart={args.rtp_start}
rtpend={args.rtp_end}
icesupport=no
""")
    write(etc / "queues.conf", """[general]
autofill=yes

[InboundQueue]
strategy=ringall
timeout=10
retry=1
""")
    write(etc / "pjsip.conf", f"""[global]
type=global
user_agent=Baudot-{args.name}

[transport-udp]
type=transport
protocol=udp
bind=127.0.0.1:{args.sip_port}

[baudot-peer]
type=endpoint
transport=transport-udp
context=from-baudot-peer
disallow=all
allow=ulaw
direct_media=no
force_rport=yes
rewrite_contact=no
outbound_proxy=sip:127.0.0.1:{args.peer_port}\\;lr
""")
    write(etc / "extensions.conf", f"""[general]
static=yes
writeprotect=yes
autofallthrough=yes

[agent-origin]
exten => {args.agent_extension},1,NoOp(Baudot synthetic ACE agent leg {args.name})
 same => n,Answer()
 same => n,Wait(15)
 same => n,Hangup()

[outbound-CA]
exten => _X.,1,NoOp(Baudot CTE-routed VRS call provider={args.provider_id} from={args.from_tn} to=${{EXTEN}})
 same => n,AGI({Path(args.agi_script).resolve()},{args.provider_id},{args.from_tn},${{EXTEN}},{args.cte_base},{Path(args.agi_trace).resolve()},VRS)
 same => n,GotoIf($["${{BAUDOT_CONNECT_ALLOWED}}" = "1"]?dial:deny)
 same => n(dial),NoOp(Baudot logical route ${{BAUDOT_ROUTE_URI}} tx=${{BAUDOT_TRANSACTION_ID}})
 same => n,Dial(PJSIP/baudot-peer/${{BAUDOT_ROUTE_URI}},8)
 same => n,Hangup()
 same => n(deny),NoOp(Baudot route denied ${{BAUDOT_ROUTE_FAILURE}})
 same => n,Hangup()

[from-phones]
exten => _X.,1,NoOp(Baudot non-VRS fail-closed path ${{EXTEN}})
 same => n,Hangup()

[from-baudot-peer]
exten => _X.,1,Hangup()
""")


if __name__ == "__main__":
    main()
