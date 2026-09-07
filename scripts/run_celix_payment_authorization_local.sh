#!/usr/bin/env bash
set -euo pipefail

: "${CELIX_PREFIX:?Set CELIX_PREFIX to an installed Apache Celix 2.4.0 prefix}"
: "${PJSIP_SOURCE_DIR:?Set PJSIP_SOURCE_DIR to the pinned pjproject checkout}"

build_dir="${BAUDOT_CELIX_BUILD_DIR:-build/celix-local}"
evidence_dir="${BAUDOT_CELIX_EVIDENCE_DIR:-build/celix-payment-evidence}"

cmake \
  -S interop/celix \
  -B "${build_dir}" \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="${CELIX_PREFIX}" \
  -DPJSIP_SOURCE_DIR="${PJSIP_SOURCE_DIR}"

cmake --build "${build_dir}" --parallel 2
mkdir -p "${evidence_dir}"

run_profile() {
  local executable="$1"
  local log="$2"
  local status=0
  local deploy_dir
  local executable_name

  deploy_dir="$(dirname "${executable}")"
  executable_name="$(basename "${executable}")"

  (
    cd "${deploy_dir}"
    timeout --signal=TERM --kill-after=2s 3s "./${executable_name}"
  ) > "${log}" 2>&1 || status=$?

  if [[ "${status}" -ne 0 && "${status}" -ne 124 ]]; then
    cat "${log}"
    return "${status}"
  fi

  if ! grep -q '"type":"baudot.celix.observation"' "${log}"; then
    cat "${log}"
    echo "No Baudot Celix observations were emitted by ${executable}" >&2
    return 1
  fi
}

run_profile \
  "${build_dir}/deploy/baudot_celix_payment_authorized_disbursement_ready/baudot_celix_payment_authorized_disbursement_ready" \
  "${evidence_dir}/payment-authorized-disbursement-ready.log"
run_profile \
  "${build_dir}/deploy/baudot_celix_payment_pending_ledger_posted/baudot_celix_payment_pending_ledger_posted" \
  "${evidence_dir}/payment-pending-ledger-posted.log"
run_profile \
  "${build_dir}/deploy/baudot_celix_payment_amount_mismatch/baudot_celix_payment_amount_mismatch" \
  "${evidence_dir}/payment-amount-mismatch.log"
run_profile \
  "${build_dir}/deploy/baudot_celix_disbursement_mapping_mismatch/baudot_celix_disbursement_mapping_mismatch" \
  "${evidence_dir}/disbursement-mapping-mismatch.log"
run_profile \
  "${build_dir}/deploy/baudot_celix_disbursement_duplicate_replay/baudot_celix_disbursement_duplicate_replay" \
  "${evidence_dir}/disbursement-duplicate-replay.log"

python3 scripts/validate_celix_payment_authorization.py \
  --ready "${evidence_dir}/payment-authorized-disbursement-ready.log" \
  --pending "${evidence_dir}/payment-pending-ledger-posted.log" \
  --amount-mismatch "${evidence_dir}/payment-amount-mismatch.log" \
  --mapping-mismatch "${evidence_dir}/disbursement-mapping-mismatch.log" \
  --duplicate-replay "${evidence_dir}/disbursement-duplicate-replay.log" \
  | tee "${evidence_dir}/payment-authorization-summary.json"
