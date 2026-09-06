# OFBiz equipment-distribution proving slice

This slice makes Apache OFBiz the reference implementation model for the **equipment-distribution** domain in Baudot's synthetic TRS business stack.

The boundary is deliberately narrow:

```text
external eligibility decision
        -> OFBiz-shaped fulfillment request
        -> product / facility / inventory
        -> order
        -> shipment
        -> return / replacement
```

and the authority rule is:

```text
inventory available
!= subscriber eligible

order created
!= subscriber eligible

shipment completed
!= subscriber eligible
```

OFBiz manages distribution state only after an external program-policy decision exists.

## Pinned upstream source

The reference profile pins the current `release24.09` branch snapshot inspected for this slice:

```text
repository: apache/ofbiz-framework
branch:     release24.09
commit:     d65f164191f331fc77da198701ab97df9bff5564
```

CI fetches the exact commit rather than following the moving branch.

The source-admission gate verifies that the pinned tree contains the OFBiz entity surfaces used by the Baudot mapping:

```text
Product
Facility
InventoryItem
InventoryItemDetail
OrderHeader
OrderItem
Shipment
ShipmentItem
ReturnHeader
ReturnItem
```

and checks the shipment and return service source surfaces as additional evidence that these are native OFBiz business domains rather than invented Baudot nouns.

## Baudot-to-OFBiz reference mapping

| Baudot equipment concern | OFBiz reference entity surface |
| --- | --- |
| Device/SKU | `Product` |
| Warehouse | `Facility` |
| Stock state | `InventoryItem`, `InventoryItemDetail` |
| Fulfillment order | `OrderHeader`, `OrderItem` |
| Outbound equipment movement | `Shipment`, `ShipmentItem` |
| Return/RMA state | `ReturnHeader`, `ReturnItem` |

This is a reference mapping, not a claim that these entities alone define a production equipment-distribution implementation.

## Synthetic contract

`testkit/business/ofbiz-equipment-distribution-v1.json` contains two synthetic device SKUs and one synthetic warehouse. All subscriber IDs, eligibility references, stock, orders, shipments, and returns exist only inside the deterministic fixture.

Eligibility is always supplied as an external evidence reference:

```text
eligibility:synthetic:<id>
```

The OFBiz-shaped reducer is forbidden from creating or inferring that decision.

## Executable scenarios

```text
EQUIP-001  eligible + in stock
           -> one order, one shipment, decrement stock

EQUIP-002  not externally eligible
           -> no order, no shipment, inventory untouched

EQUIP-003  eligible + out of stock
           -> order/backorder, no shipment

EQUIP-004  duplicate fulfillment request
           -> one order, one shipment, one inventory decrement

EQUIP-005  defective return
           -> return recorded, device quarantined, not silently restocked

EQUIP-006  defective return + replacement
           -> distinct replacement order/shipment, returned device remains quarantined
```

The reducer preserves request IDs as the idempotency seam. A replay of the same request ID cannot create a second order, shipment, or inventory decrement.

## Why the first slice is source-admitted instead of live OFBiz

OFBiz is a full ERP/business application. Booting it and asserting a random UI or internal service call would not, by itself, prove that Baudot has chosen the right domain contracts.

The first threshold therefore establishes two independent facts:

1. the chosen product/facility/inventory/order/shipment/return concepts exist in an exact upstream OFBiz source revision; and
2. Baudot's synthetic distribution state machine preserves the eligibility, inventory, return, replacement, and idempotency boundaries we require.

That keeps OFBiz replaceable and prevents its internal object model from becoming canonical Baudot semantics.

## Next threshold

A separate live OFBiz lane should:

1. build or boot the exact pinned source revision;
2. load only synthetic products, facility, inventory, parties, and addresses;
3. translate an externally authorized `EQUIP-001` request into native OFBiz product/order/shipment state;
4. read the resulting inventory and shipment state back independently;
5. execute `EQUIP-004` without double-decrementing inventory;
6. execute the defective return/replacement path; and
7. preserve upstream commit, entity/service IDs, before/after state, and independent reconciliation evidence.

The live adapter must consume a neutral Baudot fulfillment contract. OFBiz entity/service names remain implementation details.

## Claim boundary

This slice proves only the exact-source admission of the selected OFBiz equipment-domain surfaces and deterministic synthetic fulfillment semantics.

It does not establish production OFBiz compatibility, production security, subscriber eligibility, real inventory, real shipments, vendor integration, carrier tracking, accounting, provider certification, or accessibility readiness.
