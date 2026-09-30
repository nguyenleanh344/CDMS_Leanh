# Change Data Management Service (CDMS)

CDMS is a backend project focused on capturing new products and changes to product information from an inventory service.

Its purpose is to maintain the latest accepted product state and a history of meaningful changes, while preventing duplicate processing and stale updates from overwriting newer data.

The service is designed to receive product snapshots through webhook callbacks, scheduled polling, and Excel uploads, using a shared set of validation and change-processing rules. Processing status and recoverable inputs make it possible to track outcomes and resume interrupted work.

The scope covers product identity, SKU, name, and active status. Stock quantities and warehouse operations are outside this project's scope.
